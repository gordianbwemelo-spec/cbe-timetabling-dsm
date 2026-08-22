"""CBE Timetabling System — Flask backend.
Serves the web UI and a REST API backed by SQLite. Shared central data, open editing.
Run:  python app.py           (then open the printed URL on any device on your network)
Env:  PORT (default 5000), CBE_DB (default timetable.db)
"""
import os, json, io, sqlite3, socket, math, re, csv as csvmod
from flask import Flask, jsonify, request, send_from_directory, Response, g
import rules, generator

SETTINGS_DEFAULTS = {
    "seat_tolerance": "10", "max_stream_size": "120", "lab_size": "40", "classroom_size": "56",
    "module_cap": "7", "daytime_cap": "32", "evening_cap": "20",
    "soft_modules": "6", "soft_daytime": "28", "soft_evening": "16",
    "days": "Mon,Tue,Wed,Thu,Fri,Sat",
}

BASE = os.path.dirname(os.path.abspath(__file__))

def default_db():
    """Keep the database off cloud-synced folders (e.g. OneDrive) to avoid file
    locking issues. Uses a per-user local data directory; override with CBE_DB."""
    if os.environ.get("CBE_DB"):
        return os.environ["CBE_DB"]
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    d = os.path.join(base, "CBE_Timetabling")
    try:
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "timetable.db")
    except Exception:
        return os.path.join(BASE, "timetable.db")

DB = default_db()
SEED = os.path.join(BASE, "seed_data.json")
app = Flask(__name__, static_folder="static")

SESSION_FIELDS = ["semester", "day", "t", "time", "venue", "cap", "prog", "nta", "stream", "mod", "code", "instr", "occ", "est"]

# ----------------------------------------------------------------- DB
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def _close(e=None):
    d = g.pop("db", None)
    if d: d.close()

def init_db():
    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS sessions(
      id INTEGER PRIMARY KEY AUTOINCREMENT, semester TEXT, day TEXT, t INTEGER, time TEXT,
      venue TEXT, cap INTEGER, prog TEXT, nta TEXT, stream TEXT, mod TEXT, code TEXT,
      instr TEXT, occ INTEGER, est INTEGER);
    CREATE TABLE IF NOT EXISTS venues(
      semester TEXT, venue TEXT, capacity INTEGER, premises TEXT, is_lab INTEGER, type TEXT);
    CREATE TABLE IF NOT EXISTS instructors(name TEXT PRIMARY KEY, dept TEXT, qual TEXT, is_phd INTEGER, matched INTEGER);
    CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS teaching(instructor TEXT, code TEXT, module TEXT);
    CREATE TABLE IF NOT EXISTS curriculum(semester TEXT, programme TEXT, nta TEXT, code TEXT, module TEXT, credit TEXT, cls TEXT);
    CREATE TABLE IF NOT EXISTS enrolment(programme TEXT, nta TEXT, year TEXT, female TEXT, male TEXT, total INTEGER);
    CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS custom_rules(text TEXT);
    """)
    for k, v in SETTINGS_DEFAULTS.items():
        con.execute("INSERT OR IGNORE INTO settings(k, v) VALUES(?, ?)", (k, v))
    # add columns to older databases if missing
    icols = [r[1] for r in con.execute("PRAGMA table_info(instructors)")]
    if "position" not in icols:
        con.execute("ALTER TABLE instructors ADD COLUMN position TEXT")
    ecols = [r[1] for r in con.execute("PRAGMA table_info(enrolment)")]
    if "department" not in ecols:
        con.execute("ALTER TABLE enrolment ADD COLUMN department TEXT")
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    if n == 0:
        seed(con)
    seed_reference(con)
    con.close()

def base_programmes(prog):
    """Turn a timetable cohort label (which may combine programmes and streams,
    e.g. 'ACC(STRM A)+AF(STRM A)') into a clean list of base programme names
    without any stream indication: ['ACC', 'AF']."""
    p = re.sub(r"\(STRM[^)]*\)", "", prog or "", flags=re.I)
    out = []
    for part in re.split(r"[+,]", p):
        part = re.sub(r"\s+", " ", part).strip(" ,")
        if part and part not in out:
            out.append(part)
    return out

def _messy(con, table):
    return con.execute(f"SELECT COUNT(*) FROM {table} WHERE programme LIKE '%STRM%' OR programme LIKE '%+%'").fetchone()[0]

def guess_dept(prog):
    """Best-effort programme -> department (users can correct in the Enrolment editor)."""
    p = (prog or "").upper()
    def has(*xs): return any(x in p for x in xs)
    if has("HRM"): return "Business Administration"
    if has("RAM"): return "Business Administration"
    if has("BBSE", "CAED", "EDUC"): return "Education"
    if has("ICT", "BIT", "DIT", "HDIT", "TCIT", "BTCIT") or p.strip() == "IT": return "Ict & Mathematics"
    if has("MTEM", "TEM"): return "Marketing"
    if p.startswith("DM") or has("MKT", "BMK", "MARKET") or p.strip() in ("MK",): return "Marketing"
    if has("MET"): return "Legal And Industrial Metrology"
    if has("PSCM", "PROC"): return "Procurement And Supplies Management"
    if has("TLM", "TRANSPORT", "LOGIST"): return "Procurement And Supplies Management"
    if has("AF", "BAF"): return "Accountancy"
    if has("AT", "BAT"): return "Accountancy"
    if has("BF", "BBFM", "BANK"): return "Accountancy"
    if has("EF", "ECON"): return "Accountancy"
    if has("ACC", "BACC", "BCA", "ACCOUNT") or p.strip() in ("DA",): return "Accountancy"
    if has("EI", "ENTREP"): return "Business Administration"
    if p.startswith("BA") or has("BBA", "DBA", "BUSINESS ADMIN"): return "Business Administration"
    return ""

def seed_reference(con):
    """Populate the reference tables from the loaded timetable the first time
    (so the Data pages are useful immediately). Streams are NOT stored here —
    programme names are cleaned. Users then edit or re-upload real figures."""
    if con.execute("SELECT COUNT(*) FROM teaching").fetchone()[0] == 0:
        for instr, code, mod in con.execute("SELECT DISTINCT instr, code, mod FROM sessions WHERE instr!='' ORDER BY instr"):
            con.execute("INSERT INTO teaching(instructor, code, module) VALUES(?,?,?)", (instr, code or "", mod or ""))
    # curriculum: modules per (clean) programme / NTA / semester
    if con.execute("SELECT COUNT(*) FROM curriculum").fetchone()[0] == 0 or _messy(con, "curriculum"):
        con.execute("DELETE FROM curriculum"); seen = set()
        for sem, prog, nta, code, mod in con.execute("SELECT DISTINCT semester, prog, nta, code, mod FROM sessions"):
            for bp in base_programmes(prog):
                key = (sem, bp, nta or "", code or "", mod or "")
                if key in seen: continue
                seen.add(key)
                con.execute("INSERT INTO curriculum(semester, programme, nta, code, module, credit, cls) VALUES(?,?,?,?,?,?,?)",
                            (sem, bp, nta or "", code or "", mod or "", "", ""))
    # enrolment: clustered per (clean) programme / real NTA level (4-9). Foundation
    # codes such as TFC/TNC are excluded; figures are left for the user to fill.
    en_cnt = con.execute("SELECT COUNT(*) FROM enrolment").fetchone()[0]
    foundation = con.execute("SELECT COUNT(*) FROM enrolment WHERE nta LIKE '%TFC%' OR nta LIKE '%TNC%'").fetchone()[0]
    if en_cnt == 0 or _messy(con, "enrolment") or foundation:
        con.execute("DELETE FROM enrolment"); seen = set()
        rows = con.execute("SELECT DISTINCT programme, nta FROM curriculum WHERE nta LIKE 'NTA%'").fetchall()
        def keyf(r):
            m = re.search(r"NTA\s*(\d)", r[1] or ""); lvl = int(m.group(1)) if m else 9
            yr = 2 if ("Y2" in (r[1] or "") or "Yr2" in (r[1] or "")) else 1
            return (r[0] or "", lvl, yr)
        for prog, nta in sorted(rows, key=keyf):
            key = (prog, nta)
            if key in seen: continue
            seen.add(key)
            yr = "2" if ("Y2" in (nta or "") or "Yr2" in (nta or "")) else "1"
            con.execute("INSERT INTO enrolment(programme, department, nta, year, female, male, total) VALUES(?,?,?,?,?,?,?)",
                        (prog, guess_dept(prog), nta, yr, "", "", ""))
    # backfill department for any rows still missing it
    for rid, prog in con.execute("SELECT rowid, programme FROM enrolment WHERE IFNULL(department,'')=''").fetchall():
        con.execute("UPDATE enrolment SET department=? WHERE rowid=?", (guess_dept(prog), rid))
    con.commit()

def seed(con, only_sem=None):
    data = json.load(open(SEED, encoding="utf-8"))
    if only_sem:
        con.execute("DELETE FROM sessions WHERE semester=?", (only_sem,))
        con.execute("DELETE FROM venues WHERE semester=?", (only_sem,))
        sems = [only_sem]
    else:
        con.execute("DELETE FROM sessions"); con.execute("DELETE FROM venues")
        con.execute("DELETE FROM instructors"); con.execute("DELETE FROM meta")
        sems = ["I", "II"]
        con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('meta',?)", (json.dumps(data["meta"]),))
        for name, inf in data["instructors"].items():
            con.execute("INSERT OR REPLACE INTO instructors(name,dept,qual,is_phd,matched,position) VALUES(?,?,?,?,?,?)",
                        (name, inf.get("dept"), inf.get("qual"), int(bool(inf.get("is_phd"))), int(bool(inf.get("matched"))), inf.get("position", "")))
        for sem in ("I", "II"):
            con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)",
                        ("model_note_" + sem, data["semesters"][sem].get("model_note", "")))
    for sem in sems:
        S = data["semesters"][sem]
        for v in S["venues"]:
            con.execute("INSERT INTO venues VALUES(?,?,?,?,?,?)",
                        (sem, v["venue"], v["capacity"], v["premises"], int(bool(v["is_lab"])), v["type"]))
        for s in S["sessions"]:
            con.execute(f"INSERT INTO sessions({','.join(SESSION_FIELDS)}) VALUES({','.join('?'*len(SESSION_FIELDS))})",
                        (sem, s["day"], s["t"], s.get("time"), s["venue"], s.get("cap"), s.get("prog"), s.get("nta"),
                         s.get("stream"), s.get("mod"), s.get("code"), s.get("instr"), s.get("occ"), int(bool(s.get("est")))))
    con.commit()

# ----------------------------------------------------------------- helpers
def sess_rows(sem):
    return [dict(r) for r in db().execute("SELECT * FROM sessions WHERE semester=? ORDER BY id", (sem,))]

def venues(sem):
    return [{"venue": r["venue"], "capacity": r["capacity"], "premises": r["premises"],
             "is_lab": bool(r["is_lab"]), "type": r["type"]}
            for r in db().execute("SELECT * FROM venues WHERE semester=? ORDER BY capacity DESC", (sem,))]

def venmap(sem): return {v["venue"]: v for v in venues(sem)}

def instructors():
    return {r["name"]: {"dept": r["dept"], "qual": r["qual"], "is_phd": bool(r["is_phd"]), "matched": bool(r["matched"])}
            for r in db().execute("SELECT * FROM instructors")}

def meta():
    return {r["k"]: r["v"] for r in db().execute("SELECT * FROM meta")}

def clean_session(body, sem):
    t = int(body.get("t", 7))
    v = venmap(sem).get(body.get("venue"), {})
    return {"semester": sem, "day": body.get("day", "Mon"), "t": t, "time": rules.time_of(t),
            "venue": body.get("venue", ""), "cap": v.get("capacity", body.get("cap", 0)),
            "prog": body.get("prog", ""), "nta": body.get("nta", ""), "stream": body.get("stream", ""),
            "mod": body.get("mod", ""), "code": body.get("code", ""), "instr": body.get("instr", ""),
            "occ": int(body.get("occ", 0) or 0), "est": int(bool(body.get("est", 0)))}

# ----------------------------------------------------------------- API
@app.get("/api/health")
def health(): return jsonify(ok=True, service="CBE Timetabling System")

@app.get("/api/<sem>/data")
def get_data(sem):
    if sem not in ("I", "II"): return jsonify(error="bad semester"), 404
    S = sess_rows(sem); V = venues(sem); I = instructors(); M = meta()
    d = rules.derive(S, V, I, sem)
    return jsonify(sessions=S, venues=V, instructors=I,
                   meta=json.loads(M.get("meta", "{}")),
                   model_note=M.get("model_note_" + sem, ""),
                   derived=d)

@app.post("/api/<sem>/validate")
def validate_only(sem):
    body = request.get_json(force=True)
    cand = clean_session(body, sem)
    vio = rules.validate(cand, sess_rows(sem), venmap(sem), instructors(), exclude_id=body.get("id"))
    return jsonify(violations=vio)

@app.post("/api/<sem>/session")
def create(sem):
    body = request.get_json(force=True)
    cand = clean_session(body, sem)
    vio = rules.validate(cand, sess_rows(sem), venmap(sem), instructors())
    cols = ",".join(SESSION_FIELDS); qs = ",".join("?" * len(SESSION_FIELDS))
    cur = db().execute(f"INSERT INTO sessions({cols}) VALUES({qs})", tuple(cand[f] for f in SESSION_FIELDS))
    db().commit()
    return jsonify(ok=True, id=cur.lastrowid, violations=vio)

@app.put("/api/<sem>/session/<int:sid>")
def update(sem, sid):
    body = request.get_json(force=True)
    cand = clean_session(body, sem)
    vio = rules.validate({**cand, "id": sid}, sess_rows(sem), venmap(sem), instructors(), exclude_id=sid)
    sets = ",".join(f"{f}=?" for f in SESSION_FIELDS)
    db().execute(f"UPDATE sessions SET {sets} WHERE id=? AND semester=?",
                 tuple(cand[f] for f in SESSION_FIELDS) + (sid, sem))
    db().commit()
    return jsonify(ok=True, violations=vio)

@app.delete("/api/<sem>/session/<int:sid>")
def delete(sem, sid):
    db().execute("DELETE FROM sessions WHERE id=? AND semester=?", (sid, sem)); db().commit()
    return jsonify(ok=True)

@app.post("/api/<sem>/reset")
def reset(sem):
    con = sqlite3.connect(DB); seed(con, only_sem=sem); con.close()
    return jsonify(ok=True)

@app.get("/api/<sem>/export.csv")
def export_csv(sem):
    import csv
    S = sess_rows(sem); V = venmap(sem)
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Day", "Period", "Venue", "Cap", "Premises", "Cohort", "NTA", "Stream", "Module", "Code", "Instructor", "Occupancy"])
    for s in S:
        v = V.get(s["venue"], {})
        w.writerow([s["day"], rules.time_of(s["t"]), s["venue"], v.get("capacity", s["cap"]), v.get("premises", ""),
                    s["prog"], s["nta"], s["stream"], s["mod"], s["code"], s["instr"], s["occ"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=CBE_Semester_{sem}_Sessions.csv"})

@app.get("/api/<sem>/export.xlsx")
def export_xlsx(sem):
    import export_xlsx as ex
    S = sess_rows(sem); V = venues(sem); I = instructors(); M = meta()
    d = rules.derive(S, V, I, sem)
    bio = ex.build_workbook(sem, S, V, d, M.get("model_note_" + sem, ""))
    return Response(bio.getvalue(),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=CBE_Semester_{sem}_Master_Timetable.xlsx"})

# ----------------------------------------------------------------- auto-fix suggestions
DAYORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

def _busy(S, exclude_id):
    vb, ib, cb = set(), set(), set()
    for x in S:
        if x["id"] == exclude_id:
            continue
        vb.add((x["venue"], x["day"], x["t"]))
        if x["instr"]:
            ib.add((x["instr"], x["day"], x["t"]))
        cb.add((x["prog"], x["nta"], x["stream"], x["day"], x["t"]))
    return vb, ib, cb

def _venue_ok(v, sess, t):
    """Would this venue satisfy the placement rules for this session at period t?"""
    if sess["occ"] > v["capacity"] + rules.TOL:
        return False
    if v["premises"] == "Saba" and t in rules.EVE:
        return False
    if v["is_lab"] and not rules.is_it(sess):
        return False
    if "NTA9" in (sess.get("nta") or "") and v["venue"] not in ("BTA", "BTB", "BTC"):
        return False
    return True

def _allowed_slots(sess):
    """(day, t) combinations that satisfy time rules for this session."""
    nta9 = "NTA9" in (sess.get("nta") or "")
    out = []
    for day in DAYORDER:
        for t in rules.STARTS:
            if nta9 and not (t in rules.EVE or day == "Sat"):
                continue
            out.append((day, t))
    # prefer daytime and earlier in the week
    out.sort(key=lambda dt: (0 if dt[1] not in rules.EVE else 1, DAYORDER.index(dt[0]), dt[1]))
    return out

def _load_of(name, S, exclude_id):
    rows = [x for x in S if x.get("instr") == name and x["id"] != exclude_id]
    day = sum(2 for x in rows if x["t"] not in rules.EVE)
    eve = sum(2 for x in rows if x["t"] in rules.EVE)
    mods = {(x.get("mod"), x.get("code")) for x in rows}
    return len(mods), day, eve

@app.post("/api/<sem>/suggest")
def suggest(sem):
    body = request.get_json(force=True)
    sess = clean_session(body, sem)
    sid = body.get("id")
    S = sess_rows(sem); V = venues(sem); I = instructors(); vmap = {v["venue"]: v for v in V}
    vio = rules.validate({**sess, "id": sid}, S, vmap, I, exclude_id=sid)
    vb, ib, cb = _busy(S, sid)
    curV = vmap.get(sess["venue"]); prem = curV["premises"] if curV else "Main"
    rset = {x["rule"] for x in vio}
    out = []

    def free_venues(day, t, fit=None):
        s2 = dict(sess);
        if fit is not None: s2["occ"] = fit
        res = [v for v in V if v["premises"] == prem and (v["venue"], day, t) not in vb and _venue_ok(v, s2, t)]
        res.sort(key=lambda v: v["capacity"])
        return res

    # 1) VENUE CHANGE at the same slot (capacity / room clash / bad-premises placement)
    if rset & {"R5", "Room", "R6", "R8"}:
        for v in free_venues(sess["day"], sess["t"]):
            if v["venue"] != sess["venue"]:
                out.append({"type": "patch", "kind": "venue",
                            "label": f"Move to {v['venue']} [{v['capacity']}] — fits {sess['occ']}, free {sess['day']} {rules.time_of(sess['t'])}",
                            "patch": {"venue": v["venue"]}})
            if len([o for o in out if o["kind"] == "venue"]) >= 3:
                break

    # 2) SPLIT an over-capacity class into streams, each auto-placed in a free room/slot
    if "R5" in rset and curV:
        target = curV["capacity"]
        k = max(2, math.ceil(sess["occ"] / target))
        per = math.ceil(sess["occ"] / k)
        base = sess.get("stream") or "A"
        dept = I.get(sess.get("instr"), {}).get("dept")
        used_room = set()   # (venue,day,t) taken by this split plan
        used_instr = set()  # (instr,day,t) taken by this split plan
        placements = []; remaining = sess["occ"]; ok = True
        for i in range(k):
            occ_i = min(per, remaining); remaining -= occ_i
            s_i = dict(sess); s_i["occ"] = occ_i
            slot_order = ([(sess["day"], sess["t"])] if i == 0 else []) + _allowed_slots(sess)
            placed = None
            for day, t in slot_order:
                rooms = [v for v in V if v["premises"] == prem and (v["venue"], day, t) not in vb
                         and (v["venue"], day, t) not in used_room and _venue_ok(v, s_i, t)]
                rooms.sort(key=lambda v: v["capacity"])
                if not rooms:
                    continue
                room = rooms[0]
                co = ""
                if i == 0 and sess.get("instr") and (sess["instr"], day, t) not in ib and (sess["instr"], day, t) not in used_instr:
                    co = sess["instr"]
                if not co:
                    for name, inf in I.items():
                        if name == sess.get("instr"): continue
                        if dept and inf.get("dept") != dept: continue
                        if (name, day, t) in ib or (name, day, t) in used_instr: continue
                        co = name; break
                placed = {"day": day, "t": t, "venue": room["venue"], "instr": co,
                          "occ": occ_i, "stream": f"{base}/S{i+1}"}
                used_room.add((room["venue"], day, t))
                if co: used_instr.add((co, day, t))
                break
            if not placed:
                ok = False; break
            placements.append(placed)
        if ok and len(placements) == k:
            p0 = placements[0]
            update = {"venue": p0["venue"], "day": p0["day"], "t": p0["t"], "occ": p0["occ"],
                      "stream": p0["stream"], "instr": p0["instr"]}
            create = [{**sess, "id": None, **p} for p in placements[1:]]
            out.append({"type": "apply", "kind": "split",
                        "label": f"Split into {k} streams of ~{per} students (auto-placed in free rooms)",
                        "update": update, "create": create})

    # 3) MOVE TO A FREE SLOT (clash / capacity / time-rule placement)
    if rset & {"R3", "R4", "R5", "Room", "R6", "R8"}:
        for day, t in _allowed_slots(sess):
            if (sess.get("prog"), sess.get("nta"), sess.get("stream"), day, t) in cb:
                continue
            if sess.get("instr") and (sess["instr"], day, t) in ib:
                continue
            # keep current venue if it's free & ok, else first suitable free venue
            venue = None
            if (sess["venue"], day, t) not in vb and curV and _venue_ok(curV, sess, t):
                venue = sess["venue"]
            else:
                fv = free_venues(day, t)
                if fv:
                    venue = fv[0]["venue"]
            if venue and not (day == sess["day"] and t == sess["t"]):
                out.append({"type": "patch", "kind": "slot",
                            "label": f"Move to {day} {rules.time_of(t)} in {venue} (all clear)",
                            "patch": {"day": day, "t": t, "venue": venue}})
                break

    # 4) REASSIGN a lecturer (instructor clash or over a load cap)
    if rset & {"R3", "L1", "L2", "L3"}:
        dept = I.get(sess.get("instr"), {}).get("dept")
        best = None
        for name, inf in I.items():
            if name == sess.get("instr"):
                continue
            if dept and inf.get("dept") != dept:
                continue
            if (name, sess["day"], sess["t"]) in ib:
                continue
            nm, dh, eh = _load_of(name, S, sid)
            if sess["t"] in rules.EVE and eh + 2 > rules.CAP_EVE: continue
            if sess["t"] not in rules.EVE and dh + 2 > rules.CAP_DAY: continue
            score = dh + eh
            if best is None or score < best[1]:
                best = (name, score)
        if best:
            out.append({"type": "patch", "kind": "instr",
                        "label": f"Reassign to {best[0]} (same department, has spare capacity)",
                        "patch": {"instr": best[0]}})

    return jsonify(suggestions=out, violations=vio)

@app.post("/api/<sem>/apply_fix")
def apply_fix(sem):
    """Apply a multi-part fix (used by 'split'): update one session and create others."""
    body = request.get_json(force=True)
    sid = body.get("id")
    base = body.get("base") or {}
    update = body.get("update") or {}
    create = body.get("create") or []
    if sid is not None and update:
        cand = clean_session({**base, **update}, sem)
        sets = ",".join(f"{f}=?" for f in SESSION_FIELDS)
        db().execute(f"UPDATE sessions SET {sets} WHERE id=? AND semester=?",
                     tuple(cand[f] for f in SESSION_FIELDS) + (sid, sem))
    for c in create:
        cand = clean_session(c, sem)
        cols = ",".join(SESSION_FIELDS); qs = ",".join("?" * len(SESSION_FIELDS))
        db().execute(f"INSERT INTO sessions({cols}) VALUES({qs})", tuple(cand[f] for f in SESSION_FIELDS))
    db().commit()
    return jsonify(ok=True)

@app.post("/api/<sem>/autocomplete_r1")
def autocomplete_r1(sem):
    """R1: ensure every (programme,NTA,stream,module) block has 2 sessions on different
    days, same instructor. For blocks with a single session, add the second in the
    earliest free DAYTIME slot (evening for NTA9) that breaks no other rule/load cap."""
    S = sess_rows(sem); V = venues(sem); I = instructors(); vmap = {v["venue"]: v for v in V}
    vb, ib, cb = _busy(S, None)
    # instructor current hours
    dh = {}; eh = {}
    for x in S:
        if not x["instr"]: continue
        if x["t"] in rules.EVE: eh[x["instr"]] = eh.get(x["instr"], 0) + 2
        else: dh[x["instr"]] = dh.get(x["instr"], 0) + 2
    blocks = {}
    for x in S:
        blocks.setdefault((x["prog"], x["nta"], x["stream"], x["mod"], x["code"]), []).append(x)
    added = 0; unresolved = []
    for key, rows in blocks.items():
        if len(rows) != 1:
            continue
        base = rows[0]; instr = base["instr"]; occ = base["occ"]
        nta9 = "NTA9" in (base.get("nta") or "")
        periods = [17, 19] if nta9 else [7, 9, 11, 13, 15]
        prem = vmap.get(base["venue"], {}).get("premises", "Main")
        placed = None
        for day in DAYORDER:
            if day == base["day"]:
                continue
            for t in periods:
                if instr and (instr, day, t) in ib:
                    continue
                if (base["prog"], base["nta"], base["stream"], day, t) in cb:
                    continue
                if instr:  # respect load caps (R2 forces same instructor)
                    if t in rules.EVE and eh.get(instr, 0) + 2 > rules.CAP_EVE: continue
                    if t not in rules.EVE and dh.get(instr, 0) + 2 > rules.CAP_DAY: continue
                s2 = dict(base); s2["occ"] = occ
                rooms = [v for v in V if v["premises"] == prem and (v["venue"], day, t) not in vb and _venue_ok(v, s2, t)]
                if not rooms:
                    continue
                rooms.sort(key=lambda v: v["capacity"])
                room = rooms[0]
                placed = {"day": day, "t": t, "venue": room["venue"]}
                # commit to busy maps
                vb.add((room["venue"], day, t))
                if instr:
                    ib.add((instr, day, t))
                    if t in rules.EVE: eh[instr] = eh.get(instr, 0) + 2
                    else: dh[instr] = dh.get(instr, 0) + 2
                cb.add((base["prog"], base["nta"], base["stream"], day, t))
                break
            if placed:
                break
        if placed:
            cand = clean_session({**base, "id": None, "day": placed["day"], "t": placed["t"], "venue": placed["venue"]}, sem)
            cols = ",".join(SESSION_FIELDS); qs = ",".join("?" * len(SESSION_FIELDS))
            db().execute(f"INSERT INTO sessions({cols}) VALUES({qs})", tuple(cand[f] for f in SESSION_FIELDS))
            added += 1
        else:
            unresolved.append(f"{base['prog']} {base['mod']} (str {base['stream']})")
    db().commit()
    return jsonify(ok=True, added=added, unresolved=len(unresolved), unresolved_sample=unresolved[:15])

# ----------------------------------------------------------------- reference data (Data pages)
REF = {
    "instructors": {"table": "instructors", "cols": ["name", "dept", "qual", "position"], "sem": False, "ints": [],
                    "title": "Instructors & qualifications"},
    "teaching":    {"table": "teaching", "cols": ["instructor", "code", "module"], "sem": False, "ints": [],
                    "title": "Modules each instructor can teach"},
    "venues":      {"table": "venues", "cols": ["venue", "capacity", "premises", "type"], "sem": True, "ints": ["capacity"],
                    "title": "Venue names & capacity"},
    "curriculum":  {"table": "curriculum", "cols": ["programme", "nta", "code", "module", "credit", "cls"], "sem": True, "ints": [],
                    "title": "Modules per programme / NTA level"},
    "enrolment":   {"table": "enrolment", "cols": ["programme", "department", "nta", "year", "female", "male", "total"], "sem": False, "ints": ["total"],
                    "title": "Enrolment status"},
}

def _extra(entity, row, sem):
    ex = {}
    if REF[entity]["sem"]:
        ex["semester"] = sem
    if entity == "venues":
        t = (row.get("type") or "") + " " + (row.get("venue") or "")
        ex["is_lab"] = 1 if re.search(r"lab|smart", t, re.I) else 0
    if entity == "instructors":
        ex["is_phd"] = 1 if re.search(r"phd|professor|prof", row.get("qual") or "", re.I) else 0
        ex["matched"] = 1
    return ex

@app.get("/api/ref/<entity>")
def ref_list(entity):
    cfg = REF.get(entity)
    if not cfg: return jsonify(error="unknown"), 404
    sem = request.args.get("sem", "II")
    where = " WHERE semester=?" if cfg["sem"] else ""
    params = (sem,) if cfg["sem"] else ()
    rows = db().execute(f"SELECT rowid AS _id, {','.join(cfg['cols'])} FROM {cfg['table']}{where} ORDER BY rowid", params).fetchall()
    return jsonify(rows=[dict(r) for r in rows], cols=cfg["cols"], sem_scoped=cfg["sem"], title=cfg["title"])

def _coerce(entity, row):
    for c in REF[entity]["ints"]:
        row[c] = int(row.get(c) or 0) if str(row.get(c) or "").strip() not in ("", "None") else 0
    return row

@app.post("/api/ref/<entity>")
def ref_create(entity):
    cfg = REF[entity]; body = request.get_json(force=True); sem = body.get("sem", "II")
    row = _coerce(entity, {c: body.get(c, "") for c in cfg["cols"]})
    ex = _extra(entity, row, sem)
    allc = cfg["cols"] + list(ex.keys())
    vals = [row[c] for c in cfg["cols"]] + [ex[k] for k in ex]
    verb = "INSERT OR REPLACE" if entity == "instructors" else "INSERT"
    db().execute(f"{verb} INTO {cfg['table']}({','.join(allc)}) VALUES({','.join('?'*len(allc))})", vals)
    db().commit(); return jsonify(ok=True)

@app.put("/api/ref/<entity>/<int:rid>")
def ref_update(entity, rid):
    cfg = REF[entity]; body = request.get_json(force=True); sem = body.get("sem", "II")
    row = _coerce(entity, {c: body.get(c, "") for c in cfg["cols"]})
    ex = _extra(entity, row, sem)
    setcols = cfg["cols"] + list(ex.keys())
    sets = ",".join(f"{c}=?" for c in setcols)
    vals = [row[c] for c in cfg["cols"]] + [ex[k] for k in ex] + [rid]
    db().execute(f"UPDATE {cfg['table']} SET {sets} WHERE rowid=?", vals)
    db().commit(); return jsonify(ok=True)

@app.delete("/api/ref/<entity>/<int:rid>")
def ref_delete(entity, rid):
    cfg = REF[entity]
    db().execute(f"DELETE FROM {cfg['table']} WHERE rowid=?", (rid,))
    db().commit(); return jsonify(ok=True)

@app.get("/api/ref/<entity>/template.csv")
def ref_template(entity):
    cfg = REF[entity]
    buf = io.StringIO(); w = csvmod.writer(buf); w.writerow(cfg["cols"])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=CBE_{entity}_template.csv"})

@app.post("/api/ref/<entity>/import")
def ref_import(entity):
    cfg = REF[entity]; body = request.get_json(force=True)
    text = body.get("csv", ""); mode = body.get("mode", "replace"); sem = body.get("sem", "II")
    reader = csvmod.DictReader(io.StringIO(text))
    # map incoming headers (case/space-insensitive) to our columns
    norm = {re.sub(r"[^a-z0-9]", "", (h or "").lower()): h for h in (reader.fieldnames or [])}
    def pick(colname):
        return norm.get(re.sub(r"[^a-z0-9]", "", colname.lower()))
    hmap = {c: pick(c) for c in cfg["cols"]}
    if mode == "replace":
        if cfg["sem"]:
            db().execute(f"DELETE FROM {cfg['table']} WHERE semester=?", (sem,))
        else:
            db().execute(f"DELETE FROM {cfg['table']}")
    count = 0
    for rec in reader:
        row = _coerce(entity, {c: (rec.get(hmap[c], "") if hmap[c] else "") for c in cfg["cols"]})
        if not any(str(v).strip() for v in row.values()):
            continue
        ex = _extra(entity, row, sem)
        allc = cfg["cols"] + list(ex.keys())
        vals = [row[c] for c in cfg["cols"]] + [ex[k] for k in ex]
        verb = "INSERT OR REPLACE" if entity == "instructors" else "INSERT"
        db().execute(f"{verb} INTO {cfg['table']}({','.join(allc)}) VALUES({','.join('?'*len(allc))})", vals)
        count += 1
    db().commit(); return jsonify(ok=True, imported=count)

@app.get("/api/modules")
def modules_all():
    rows = db().execute("""SELECT code, module FROM curriculum GROUP BY code, module
                           ORDER BY module""").fetchall()
    return jsonify(rows=[{"code": r["code"], "module": r["module"]} for r in rows if r["module"]])

@app.get("/api/<sem>/catalogue")
def catalogue(sem):
    rows = db().execute("""SELECT code, module, MAX(credit) AS credit, COUNT(*) AS uses
                           FROM curriculum WHERE semester=? GROUP BY code, module ORDER BY module""", (sem,)).fetchall()
    return jsonify(rows=[dict(r) for r in rows])

@app.get("/api/<sem>/streams")
def streams(sem):
    S = sess_rows(sem); V = venues(sem)
    maxcap = max([v["capacity"] for v in V], default=100)
    enr = {(r["programme"], r["nta"]): r["total"] for r in db().execute("SELECT programme, nta, total FROM enrolment")}
    agg = {}
    for s in S:
        key = (s["prog"], s["nta"])
        d = agg.setdefault(key, {"streams": set(), "sessions": 0})
        d["streams"].add(s["stream"]); d["sessions"] += 1
    out = []
    for (prog, nta), d in sorted(agg.items()):
        total = enr.get((prog, nta), 0)
        suggested = max(1, math.ceil(total / maxcap)) if total else ""
        out.append({"programme": prog, "nta": nta, "enrolment": total,
                    "streams_present": ", ".join(sorted(d["streams"])), "n_present": len(d["streams"]),
                    "suggested": suggested, "sessions": d["sessions"]})
    return jsonify(rows=out, maxcap=maxcap)

def get_settings():
    s = dict(SETTINGS_DEFAULTS)
    for r in db().execute("SELECT k, v FROM settings"):
        s[r["k"]] = r["v"]
    return s

@app.get("/api/settings")
def settings_get():
    return jsonify(settings=get_settings(),
                   rules=[{"_id": r["rowid"], "text": r["text"]} for r in db().execute("SELECT rowid, text FROM custom_rules ORDER BY rowid")])

@app.put("/api/settings")
def settings_put():
    b = request.get_json(force=True)
    for k, v in (b.get("settings") or {}).items():
        db().execute("INSERT OR REPLACE INTO settings(k, v) VALUES(?, ?)", (k, str(v)))
    db().commit(); return jsonify(ok=True)

@app.post("/api/rules")
def rules_add():
    b = request.get_json(force=True); txt = (b.get("text") or "").strip()
    if txt: db().execute("INSERT INTO custom_rules(text) VALUES(?)", (txt,)); db().commit()
    return jsonify(ok=True)

@app.delete("/api/rules/<int:rid>")
def rules_del(rid):
    db().execute("DELETE FROM custom_rules WHERE rowid=?", (rid,)); db().commit(); return jsonify(ok=True)

@app.post("/api/<sem>/generate")
def generate_tt(sem):
    if sem not in ("I", "II"):
        return jsonify(error="bad semester"), 404
    cur = [dict(r) for r in db().execute("SELECT programme, nta, code, module FROM curriculum WHERE semester=?", (sem,))]
    enr = [dict(r) for r in db().execute("SELECT programme, nta, total FROM enrolment")]
    teach = [dict(r) for r in db().execute("SELECT instructor, code, module FROM teaching")]
    result = generator.generate(sem, venues(sem), instructors(), teach, cur, enr, get_settings())
    # write generated sessions in place of the current ones for this semester
    db().execute("DELETE FROM sessions WHERE semester=?", (sem,))
    cols = ",".join(SESSION_FIELDS); qs = ",".join("?" * len(SESSION_FIELDS))
    for s in result["sessions"]:
        s = {**s, "semester": sem}
        db().execute(f"INSERT INTO sessions({cols}) VALUES({qs})", tuple(s.get(f) for f in SESSION_FIELDS))
    db().commit()
    return jsonify(ok=True, stats=result["stats"], flags_count=len(result["flags"]),
                   flags_sample=[f["detail"] for f in result["flags"][:20]])

@app.post("/api/rename/instructor")
def rename_instructor():
    b = request.get_json(force=True)
    old = (b.get("old") or "").strip(); new = (b.get("new") or "").strip()
    if not old or not new or old == new:
        return jsonify(ok=True, sessions=0, teaching=0)
    s = db().execute("UPDATE sessions SET instr=? WHERE instr=?", (new, old)).rowcount
    t = db().execute("UPDATE teaching SET instructor=? WHERE instructor=?", (new, old)).rowcount
    if db().execute("SELECT 1 FROM instructors WHERE name=?", (new,)).fetchone():
        db().execute("DELETE FROM instructors WHERE name=?", (old,))
    else:
        db().execute("UPDATE instructors SET name=? WHERE name=?", (new, old))
    db().commit()
    return jsonify(ok=True, sessions=s, teaching=t)

@app.post("/api/rename/module")
def rename_module():
    b = request.get_json(force=True)
    om = (b.get("old_module") or "").strip(); oc = (b.get("old_code") or "")
    nm = (b.get("new_module") or om).strip(); nc = (b.get("new_code") or "")
    if not om and not oc:
        return jsonify(ok=True)
    def upd(table, mcol, ccol):
        if oc:
            return db().execute(f"UPDATE {table} SET {mcol}=?, {ccol}=? WHERE {mcol}=? AND IFNULL({ccol},'')=?",
                                (nm, nc, om, oc)).rowcount
        return db().execute(f"UPDATE {table} SET {mcol}=?, {ccol}=? WHERE {mcol}=?", (nm, nc, om)).rowcount
    s = upd("sessions", "mod", "code"); c = upd("curriculum", "module", "code"); t = upd("teaching", "module", "code")
    db().commit()
    return jsonify(ok=True, sessions=s, curriculum=c, teaching=t)

@app.get("/api/<sem>/reports")
def reports(sem):
    from collections import defaultdict
    def iv(x):
        try: return int(x)
        except (TypeError, ValueError): return 0
    enr = [dict(r) for r in db().execute("SELECT programme, department, nta, year, female, male, total FROM enrolment")]
    tot = sum(iv(r["total"]) for r in enr); tf = sum(iv(r["female"]) for r in enr); tm = sum(iv(r["male"]) for r in enr)
    bd = defaultdict(lambda: {"total": 0, "f": 0, "m": 0, "progs": set()})
    for r in enr:
        d = r["department"] or "(unassigned)"
        bd[d]["total"] += iv(r["total"]); bd[d]["f"] += iv(r["female"]); bd[d]["m"] += iv(r["male"]); bd[d]["progs"].add(r["programme"])
    by_dept = [{"department": k, "total": v["total"], "female": v["f"], "male": v["m"], "programmes": len(v["progs"])}
               for k, v in sorted(bd.items())]
    bp = defaultdict(lambda: {"total": 0, "dept": ""})
    for r in enr:
        bp[r["programme"]]["total"] += iv(r["total"]); bp[r["programme"]]["dept"] = r["department"]
    by_prog = [{"programme": k, "department": v["dept"], "total": v["total"]} for k, v in sorted(bp.items())]
    bn = defaultdict(int)
    for r in enr: bn[r["nta"] or "?"] += iv(r["total"])
    by_nta = [{"nta": k, "total": v} for k, v in sorted(bn.items())]
    st = [dict(r) for r in db().execute("SELECT dept, is_phd FROM instructors")]
    sd = defaultdict(lambda: {"count": 0, "phd": 0})
    for r in st:
        d = r["dept"] or "(unassigned)"; sd[d]["count"] += 1; sd[d]["phd"] += 1 if r["is_phd"] else 0
    staff_by_dept = [{"department": k, "count": v["count"], "phd": v["phd"]} for k, v in sorted(sd.items())]
    V = venues(sem)
    vprem = defaultdict(lambda: {"count": 0, "cap": 0})
    for v in V: vprem[v["premises"]]["count"] += 1; vprem[v["premises"]]["cap"] += v["capacity"]
    venues_summary = {"count": len(V), "capacity": sum(v["capacity"] for v in V), "labs": sum(1 for v in V if v["is_lab"]),
                      "by_premises": [{"premises": k, "count": v["count"], "capacity": v["cap"]} for k, v in sorted(vprem.items())]}
    ncat = db().execute("SELECT COUNT(*) FROM (SELECT 1 FROM curriculum WHERE semester=? GROUP BY code, module)", (sem,)).fetchone()[0]
    nteach = db().execute("SELECT COUNT(*) FROM teaching").fetchone()[0]
    d = rules.derive(sess_rows(sem), V, instructors(), sem); m = d["metrics"]
    return jsonify(semester=sem,
        enrolment={"total": tot, "female": tf, "male": tm, "programmes": len(bp),
                   "by_department": by_dept, "by_programme": by_prog, "by_nta": by_nta},
        staff={"total": len(st), "phd": sum(1 for r in st if r["is_phd"]), "by_department": staff_by_dept},
        venues=venues_summary, modules={"catalogue": ncat, "teaching_links": nteach},
        timetable={"sessions": m["sessions"], "utilisation": m["util"], "peak": m["peak"],
                   "instructors": m["instructors"], "hard": m["hard"], "review": m["review"],
                   "overloads": m["overloads"], "vacant": m["vacant"]})

# ----------------------------------------------------------------- static
FRONTEND = {"index.html", "app.js", "style.css"}
def _serve(name):
    for d in (BASE, os.path.join(BASE, "static")):
        if os.path.exists(os.path.join(d, name)):
            return send_from_directory(d, name)
    return ("Not found", 404)

@app.get("/")
def index(): return _serve("index.html")

@app.get("/<path:p>")
def front(p):
    return _serve(p) if p in FRONTEND else ("Not found", 404)

def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        return "127.0.0.1"

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    ip = lan_ip()
    print("\n" + "=" * 60)
    print("  CBE TIMETABLING SYSTEM is running.")
    print(f"  On this computer:      http://localhost:{port}")
    print(f"  On other devices:      http://{ip}:{port}   (same Wi-Fi/network)")
    print("  Press CTRL+C to stop.")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)
