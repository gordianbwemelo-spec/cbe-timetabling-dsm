"""Timetable generator for the CBE system.
From the reference data (enrolment, venues, curriculum, teaching capability, staff)
it sizes streams, MERGES shared classes to save cost, allocates venues and
instructors under the rules and load caps, and red-flags anything that cannot be
placed or staffed. Greedy, deterministic.

Rules honoured (besides venue capacity / seat tolerance):
  * A stream (programme+NTA) has at most 3 back-to-back sessions in a day.
  * An INSTRUCTOR has at most 3 back-to-back sessions in a day.
  * An instructor cannot teach at Main and at Saba Saba the same day unless there
    is at least a 2-hour gap between the two sessions (else a different day).
  * On-duty instructors are allocated first; part-timers/volunteers only after.
  * Computer labs are used only for IT-practical modules, which prefer a lab.
  * NTA Level 9 is taught only by PhD holders / professors, and sits in the
    EVENING (Mon-Fri 17:00+) or on SATURDAY only.
  * Tutorial Assistants teach only NTA Level 4, 5 or 6 - nothing above.
  * Instructors on study leave are never allocated.
  * 17:00-onwards and Saturday sessions go to evening streams.

Cost-saving MERGES (the college pays per session, so fewer sessions = less cost):
  * Cross-cutting: the SAME module at the SAME NTA level, taught to more than one
    programme/stream, is combined into ONE session when a venue can hold the
    combined class.
  * Full-time + evening: the same module for a day stream and an evening stream is
    combined into one (evening) session when a venue can hold them together.
  A merged session is recorded once (one lecturer, one room) and its cohort label
  lists every participating programme/stream, e.g. "ACC(STRM A)+AF(STRM A)".

Streams are sized from the SHARED enrolment table (not the per-semester
curriculum), so the streams created for Semester I do not change in Semester II.
"""
import math, re
from collections import defaultdict
import rules

DAY_T = [7, 9, 11, 13, 15]
EVE_T = [17, 19]
EVE = set(EVE_T)
ALL_T = DAY_T + EVE_T
PROF = {"professor", "associate professor"}
TRAVEL_GAP = 4   # different-premises sessions the same day must start >= 4h apart (>=2h to travel)

def _nta9_venue(vn):
    vn = vn or ""
    return vn in ("BTA", "BTB", "BTC", "BLOCK E") or vn.startswith("B2-5")

def time_of(t):
    return f"{t:02d}:00-{t+2:02d}:00"

def generate(sem, venues, instructors, teaching, curriculum, enrolment, settings):
    def sget(k, d):
        try:
            return int(settings.get(k, d))
        except (TypeError, ValueError):
            return d
    tol = sget("seat_tolerance", 10)
    _halls = [v["capacity"] for v in venues if not v["is_lab"]]
    largest_hall = max(_halls) if _halls else 100
    _pg = [v["capacity"] for v in venues if _nta9_venue(v["venue"])]
    largest_pg = max(_pg) if _pg else 56
    # Stream sizing uses a semester-independent capacity (the largest room that
    # exists in ANY semester, passed by the caller) so the streams created for
    # Semester I do not change in Semester II.  Placement still uses this
    # semester's actual rooms.
    sz_hall = sget("_hall_cap", 0) or largest_hall
    sz_pg = sget("_pg_cap", 0) or largest_pg
    try:
        user_cap = int(settings.get("max_stream_size"))
    except (TypeError, ValueError):
        user_cap = 0
    cap_mod = sget("module_cap", 7)
    cap_day = sget("daytime_cap", 32)
    cap_eve = sget("evening_cap", 20)
    DAYS = [d.strip() for d in (settings.get("days") or "Mon,Tue,Wed,Thu,Fri,Sat").split(",") if d.strip()]

    V = list(venues)

    def _lvl(x):
        m = re.search(r"(\d)", x or "")
        return m.group(1) if m else None
    def _lvlnum(x):
        m = re.search(r"(\d)", x or "")
        return int(m.group(1)) if m else 0

    can = defaultdict(list)
    _cap_seen = set()
    can_count = defaultdict(int)
    for t in teaching:
        n = t.get("instructor")
        if not n:
            continue
        tl = _lvl(t.get("nta"))
        if t.get("module"):
            can[("m", t["module"].strip().lower())].append((n, tl))
        if t.get("code"):
            can[("c", t["code"].strip().lower())].append((n, tl))
        key = (t.get("code") or "").strip().lower() or ("m:" + (t.get("module") or "").strip().lower())
        if key.strip(":") and (n, key) not in _cap_seen:
            _cap_seen.add((n, key)); can_count[n] += 1

    enr, enr_eve = {}, {}
    for e in enrolment:
        key = (e["programme"], e["nta"])
        try:
            enr[key] = int(e["total"])
        except (TypeError, ValueError):
            enr[key] = 0
        try:
            enr_eve[key] = int(e.get("evening") or 0)
        except (TypeError, ValueError):
            enr_eve[key] = 0

    cur = defaultdict(list)
    for c in curriculum:
        cur[(c["programme"], c["nta"])].append(c)

    # ---- helpers -----------------------------------------------------------
    def is_it(nta, mod, code):
        return rules.is_it({"prog": "", "nta": nta, "mod": mod, "code": code})

    def _status(inf):
        return (inf.get("status") or "On duty")

    def _phd_or_prof(inf):
        if inf.get("is_phd"):
            return True
        if "phd" in (inf.get("qual") or "").lower():
            return True
        return (inf.get("position") or "").strip().lower() in PROF

    def venue_ok(v, size, nta, mod, code, t):
        if size > v["capacity"] + tol:
            return False
        if v["premises"] == "Saba" and t in EVE:
            return False
        if v["is_lab"] and not is_it(nta, mod, code):
            return False
        if "NTA9" in (nta or "") and not _nta9_venue(v["venue"]):
            return False
        return True

    def mod_limit(name):
        try:
            return int(instructors.get(name, {}).get("module_limit"))
        except (TypeError, ValueError):
            return cap_mod

    def avail(name):
        inf = instructors.get(name, {})
        days = {d.strip() for d in (inf.get("avail_days") or "").split(",") if d.strip()}
        pers = set()
        for x in (inf.get("avail_periods") or "").split(","):
            m = re.search(r"\d+", x)
            if m:
                pers.add(int(m.group()))
        return days, pers

    def eligible(nta, mod, code):
        slvl = _lvl(nta)
        lvln = _lvlnum(nta)
        cands = list(can.get(("m", (mod or "").strip().lower()), [])) + list(can.get(("c", (code or "").strip().lower()), []))
        out = []
        for n, tl in cands:
            if n in out:
                continue
            if tl and slvl and tl != slvl:
                continue
            inf = instructors.get(n, {})
            if _status(inf) == "Study leave":
                continue
            if "NTA9" in (nta or "") and not _phd_or_prof(inf):
                continue
            if (inf.get("position") or "").strip().lower() == "tutorial assistant" and lvln > 6:
                continue
            out.append(n)
        return out

    def rank(n):
        inf = instructors.get(n, {})
        st = 0 if _status(inf) == "On duty" else 1     # on-duty first, part-timers after
        return (st, can_count.get(n, 999), iday[n] + ieve[n])

    # ---- 1. Build stream-units from the SHARED enrolment (stable across sem) --
    units = []   # each: {prog, nta, stream, evening, size, mods}
    stats = {"cohorts": 0, "streams": 0, "modules": 0,
             "sessions_needed": 0, "sessions_placed": 0, "sessions_saved": 0}
    for (prog, nta), mods in sorted(cur.items()):
        stats["cohorts"] += 1
        nta9 = "NTA9" in (nta or "")
        day_ct = enr.get((prog, nta), 0)
        eve_ct = enr_eve.get((prog, nta), 0)
        subs = []
        if nta9:
            subs.append((True, day_ct + eve_ct))          # NTA9: evening + Saturday only
        else:
            if day_ct > 0:
                subs.append((False, day_ct))
            if eve_ct > 0:
                subs.append((True, eve_ct))
            if day_ct <= 0 and eve_ct <= 0:
                flags_no = f"{prog} {nta}: no enrolment figure - cannot size streams."
                units.append({"prog": prog, "nta": nta, "stream": "", "evening": False,
                              "size": largest_hall, "mods": mods, "_flag": flags_no})
                continue
        room_max = sz_pg if nta9 else sz_hall
        target = room_max if user_cap <= 0 else min(user_cap, room_max)
        target = max(1, target)
        for (evening, headcount) in subs:
            nstreams = max(1, math.ceil(headcount / target))
            size = math.ceil(headcount / nstreams)
            stats["streams"] += nstreams
            for si in range(nstreams):
                if evening:
                    stream = "EVE" if nstreams == 1 else ("EVE " + chr(65 + si))
                else:
                    stream = "" if nstreams == 1 else ("STRM " + chr(65 + si))
                units.append({"prog": prog, "nta": nta, "stream": stream,
                              "evening": evening, "size": size, "mods": mods})

    sessions, flags = [], []
    for u in units:
        if u.get("_flag"):
            flags.append({"type": "NO_ENROLMENT", "detail": u["_flag"], "severity": "review"})

    # ---- 2. Demand per (nta, module); merge cross-cutting + full-time/evening --
    demand = defaultdict(list)     # (nta, mkey) -> [ {u, mod, code} ]
    for u in units:
        for c in u["mods"]:
            mod, code = c.get("module", ""), c.get("code", "")
            mkey = (code or "").strip().lower() or ("m:" + (mod or "").strip().lower())
            if not mkey.strip(":"):
                continue
            demand[(u["nta"], mkey)].append({"u": u, "mod": mod, "code": code})

    merge_ft_eve = str(settings.get("merge_ft_evening", "1")).strip().lower() not in ("0", "false", "no", "off")

    def ffd(items, cap):
        """First-fit-decreasing bin packing of same-mode demands into rooms."""
        items = sorted(items, key=lambda d: -d["u"]["size"])
        bins = []   # each: {"members":[d...], "size":int}
        for d in items:
            s = d["u"]["size"]
            placed = False
            for b in bins:
                if b["size"] + s <= cap:
                    b["members"].append(d); b["size"] += s; placed = True; break
            if not placed:
                bins.append({"members": [d], "size": s})
        return bins

    groups = []   # each: {nta, mod, code, evening, size, members:[unit...]}
    total_pairs = 0
    for (nta, mkey), ds in sorted(demand.items()):
        nta9 = "NTA9" in (nta or "")
        cap = (sz_pg if nta9 else sz_hall) + tol
        total_pairs += len(ds)
        rep = next((d for d in ds if d["code"]), ds[0])
        # Cross-cutting merge WITHIN each mode: day classes stay daytime, evening
        # classes stay evening.  Nothing daytime is pushed to the evening here.
        day_bins = ffd([d for d in ds if not d["u"]["evening"]], cap)
        eve_bins = ffd([d for d in ds if d["u"]["evening"]], cap)
        # Full-time + evening merge: only when this module genuinely HAS an evening
        # section, fold whichever daytime bins still fit into an evening bin (the
        # combined class then meets in the evening).  Bigger evening bins first.
        if merge_ft_eve and eve_bins and day_bins:
            for eb in sorted(eve_bins, key=lambda b: -b["size"]):
                for db in sorted(day_bins, key=lambda b: -b["size"]):
                    if db in day_bins and eb["size"] + db["size"] <= cap:
                        eb["members"] += db["members"]; eb["size"] += db["size"]
                        day_bins.remove(db)
        for evening, bins in ((False, day_bins), (True, eve_bins)):
            for b in bins:
                groups.append({"nta": nta, "mod": rep["mod"], "code": rep["code"],
                               "evening": evening or any(d["u"]["evening"] for d in b["members"]),
                               "size": b["size"], "members": [d["u"] for d in b["members"]]})

    # ---- 3. Schedule each group ONCE (one lecturer, one room, 2 sessions) -----
    vbusy, sbusy = set(), set()
    ibusy = set()
    iplaced = defaultdict(list)
    iday, ieve, imod = defaultdict(int), defaultdict(int), defaultdict(set)

    def travel_ok(instr, day, t, P):
        for (dd, tt, pp) in iplaced[instr]:
            if dd == day and pp and P and pp != P and abs(tt - t) < TRAVEL_GAP:
                return False
        return True

    for g in sorted(groups, key=lambda x: (x["nta"], 0 if x["evening"] else 1, -x["size"], x["mod"])):
        stats["modules"] += 1
        stats["sessions_needed"] += 2
        nta = g["nta"]; mod = g["mod"]; code = g["code"]
        evening = g["evening"]; size = g["size"]; members = g["members"]
        gkey = (nta, (code or "").strip().lower() or ("m:" + (mod or "").strip().lower()))
        cand = sorted(eligible(nta, mod, code), key=rank)
        done = False
        for instr in cand:
            new_mod = gkey not in imod[instr]
            if new_mod and len(imod[instr]) >= mod_limit(instr):
                continue
            adays, apers = avail(instr)
            placed = []
            used_days = set()
            # spread the 2 sessions onto the least-loaded days across all members
            def day_load(d):
                return sum(1 for (p, n, s2, dd, tt) in sbusy
                           if dd == d and any((p, n, s2) == (u["prog"], u["nta"], u["stream"]) for u in members))
            for day in sorted(DAYS, key=day_load):
                if len(placed) == 2:
                    break
                if day in used_days:
                    continue
                if adays and day not in adays:
                    continue
                # times already used by any member on this day (for idle-clustering + consecutive)
                member_ts = [tt for (p, n, s2, dd, tt) in sbusy
                             if dd == day and any((p, n, s2) == (u["prog"], u["nta"], u["stream"]) for u in members)]
                i_day_ts = [tt for (nn, dd, tt) in ibusy if nn == instr and dd == day]

                def slot_pen(t, _ex=tuple(member_ts)):
                    return (min((abs(t - x) for x in _ex), default=0), t)

                for t in sorted(ALL_T, key=slot_pen):
                    if evening and not (day == "Sat" or t in EVE):
                        continue
                    if apers and t not in apers:
                        continue
                    if (instr, day, t) in ibusy:
                        continue
                    if any((u["prog"], u["nta"], u["stream"], day, t) in sbusy for u in members):
                        continue
                    # no member stream exceeds 3 back-to-back sessions
                    bad = False
                    for u in members:
                        ex_u = [tt for (p, n, s2, dd, tt) in sbusy if (p, n, s2, dd) == (u["prog"], u["nta"], u["stream"], day)]
                        if rules.max_consecutive(ex_u + [t]) > rules.MAX_CONSEC:
                            bad = True; break
                    if bad:
                        continue
                    if rules.max_consecutive(i_day_ts + [t]) > rules.MAX_CONSEC:
                        continue
                    if t in EVE and ieve[instr] + 2 > cap_eve:
                        continue
                    if t not in EVE and iday[instr] + 2 > cap_day:
                        continue
                    rooms = [v for v in V
                             if (v["venue"], day, t) not in vbusy
                             and venue_ok(v, size, nta, mod, code, t)
                             and travel_ok(instr, day, t, v["premises"])]
                    if not rooms:
                        continue
                    it_mod = is_it(nta, mod, code)
                    rooms.sort(key=lambda v: (0 if (it_mod and v["is_lab"]) else 1, v["capacity"]))
                    v = rooms[0]
                    placed.append((day, t, v)); used_days.add(day); break
            if len(placed) == 2:
                # cohort label: one member -> plain; several -> merged label
                if len(members) == 1:
                    u = members[0]
                    prog_lbl, stream_lbl, occ = u["prog"], u["stream"], u["size"]
                else:
                    prog_lbl = "+".join((f"{u['prog']}({u['stream']})" if u["stream"] else u["prog"]) for u in members)
                    stream_lbl, occ = "", size
                for (day, t, v) in placed:
                    vbusy.add((v["venue"], day, t))
                    ibusy.add((instr, day, t))
                    iplaced[instr].append((day, t, v["premises"]))
                    for u in members:
                        sbusy.add((u["prog"], u["nta"], u["stream"], day, t))
                    if t in EVE:
                        ieve[instr] += 2
                    else:
                        iday[instr] += 2
                    sessions.append({"day": day, "t": t, "time": time_of(t), "venue": v["venue"], "cap": v["capacity"],
                                     "prog": prog_lbl, "nta": nta, "stream": stream_lbl, "mod": mod, "code": code,
                                     "instr": instr, "occ": occ, "est": 1})
                imod[instr].add(gkey)
                stats["sessions_placed"] += 2
                done = True
                break
        if not done:
            lbl = "+".join((f"{u['prog']}({u['stream']})" if u["stream"] else u["prog"]) for u in members)
            if not cand:
                ftype, reason = "NO_CAPABLE_STAFF", "no qualified, on-duty lecturer can teach this - add teaching capability or a part-timer"
            elif all((len(imod[n]) >= mod_limit(n)) or (iday[n] >= cap_day and ieve[n] >= cap_eve) for n in cand):
                ftype, reason = "PART_TIMER_NEEDED", "all qualified lecturers are at capacity - a PART-TIMER is needed"
            else:
                ftype, reason = "UNPLACED", "no free room/time slot within the rules"
            flags.append({"type": ftype, "detail": f"{lbl} {nta} - {mod}: {reason}.", "severity": "hard"})

    stats["sessions_saved"] = 2 * (total_pairs - len(groups))
    stats["sessions_flagged"] = stats["sessions_needed"] - stats["sessions_placed"]
    return {"sessions": sessions, "flags": flags, "stats": stats}
