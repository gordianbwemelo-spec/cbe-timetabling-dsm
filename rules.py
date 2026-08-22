"""Shared timetabling rules: validation of a single session and full derivation
(workload, venue-utilisation, red-flags, metrics). Used by the API server."""
import re
from collections import defaultdict

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
STARTS = [7, 9, 11, 13, 15, 17, 19]
PERIODS = [f"{t:02d}:00-{t+2:02d}:00" for t in STARTS]
EVE = {17, 19}
CAP_MOD, CAP_DAY, CAP_EVE = 7, 32, 20
SOFT_MOD, SOFT_DAY, SOFT_EVE = 6, 28, 16
TOL = 10

ITPROG = re.compile(r"\bICT\b|\bIT\b|BScIT|\bBIT\b|\bDIT\b|HDIT|TCIT|BTCIT|Information Technology|ITPMGT|MBI|IT-", re.I)
ITKW = re.compile(r"program|network|database|web|multimedia|graphic|software|data structure|operating system|"
                  r"system analys|data mining|warehous|analytic|cyber|cloud|machine learning|artificial intel|"
                  r"mobile app|e-commerce", re.I)

def time_of(t): return f"{t:02d}:00-{t+2:02d}:00"
def prog_is_it(s): return bool(ITPROG.search((s.get("prog") or "") + " " + (s.get("nta") or "")))
def is_it(s): return prog_is_it(s) or bool(ITKW.search((s.get("mod") or "") + " " + (s.get("code") or "")))


def validate(sess, sessions, venmap, instructors, exclude_id=None):
    """Return a list of {rule, hard, msg} for a single (candidate) session."""
    out = []
    v = venmap.get(sess["venue"])
    others = [x for x in sessions if x.get("id") != exclude_id]
    def clash(f): return any(f(x) for x in others)
    if sess.get("instr") and clash(lambda x: x.get("instr") == sess["instr"] and x["day"] == sess["day"] and x["t"] == sess["t"]):
        out.append({"rule": "R3", "hard": True, "msg": f"Instructor {sess['instr']} is already teaching at {sess['day']} {time_of(sess['t'])}."})
    if clash(lambda x: x["venue"] == sess["venue"] and x["day"] == sess["day"] and x["t"] == sess["t"]):
        out.append({"rule": "Room", "hard": True, "msg": f"{sess['venue']} is already occupied at {sess['day']} {time_of(sess['t'])}."})
    if clash(lambda x: x.get("prog") == sess.get("prog") and x.get("nta") == sess.get("nta") and x.get("stream") == sess.get("stream") and x["day"] == sess["day"] and x["t"] == sess["t"]):
        out.append({"rule": "R4", "hard": True, "msg": f"Cohort {sess.get('prog')} ({sess.get('nta')} str {sess.get('stream')}) is already booked at {sess['day']} {time_of(sess['t'])}."})
    if v and sess["occ"] > v["capacity"] + TOL:
        out.append({"rule": "R5", "hard": True, "msg": f"Occupancy {sess['occ']} exceeds {sess['venue']} capacity {v['capacity']} (+10 tolerance)."})
    if v and v["premises"] == "Saba" and sess["t"] in EVE:
        out.append({"rule": "R6", "hard": True, "msg": f"Saba Saba venues must end by 17:00 — {time_of(sess['t'])} is not allowed."})
    if v and v["is_lab"] and not is_it(sess):
        out.append({"rule": "R7", "hard": False, "msg": f"{sess['venue']} is a lab/smart room — reserve for hands-on IT ('{sess.get('mod')}' looks non-IT)."})
    if "NTA9" in (sess.get("nta") or ""):
        if sess["venue"] not in ("BTA", "BTB", "BTC"):
            out.append({"rule": "R8", "hard": True, "msg": f"Master's (NTA9) must be in BTA, BTB or BTC (not {sess['venue']})."})
        if not (sess["t"] in EVE or sess["day"] == "Sat"):
            out.append({"rule": "R8", "hard": True, "msg": f"Master's (NTA9) must run in the evening or on Saturday (not {sess['day']} {time_of(sess['t'])})."})
        inf = instructors.get(sess.get("instr"))
        if inf and inf.get("matched") and not inf.get("is_phd"):
            out.append({"rule": "R9", "hard": False, "msg": f"Master's module assigned to {sess['instr']}, not recorded as a PhD holder."})
    if prog_is_it(sess):
        inf = instructors.get(sess.get("instr"))
        if inf and inf.get("matched") and inf.get("dept") and inf["dept"] != "Ict & Mathematics":
            out.append({"rule": "R9", "hard": False, "msg": f"IT-programme module assigned to {sess['instr']} ({inf['dept']}), not ICT staff."})
    if sess.get("instr"):
        rows = [x for x in others if x.get("instr") == sess["instr"]] + [sess]
        mods = {(x.get("mod"), x.get("code")) for x in rows}
        day = sum(2 for x in rows if x["t"] not in EVE)
        eve = sum(2 for x in rows if x["t"] in EVE)
        if len(mods) > CAP_MOD: out.append({"rule": "L1", "hard": True, "msg": f"{sess['instr']} would teach {len(mods)} modules (cap 7)."})
        elif len(mods) >= SOFT_MOD: out.append({"rule": "L1", "hard": False, "msg": f"{sess['instr']} at {len(mods)} modules (soft limit 6)."})
        if day > CAP_DAY: out.append({"rule": "L2", "hard": True, "msg": f"{sess['instr']} would reach {day}h daytime (cap 32h)."})
        elif day >= SOFT_DAY: out.append({"rule": "L2", "hard": False, "msg": f"{sess['instr']} at {day}h daytime (soft 28h)."})
        if eve > CAP_EVE: out.append({"rule": "L3", "hard": True, "msg": f"{sess['instr']} would reach {eve}h evening (cap 20h)."})
        elif eve >= SOFT_EVE: out.append({"rule": "L3", "hard": False, "msg": f"{sess['instr']} at {eve}h evening (soft 16h)."})
    return out


def derive(sessions, venues, instructors, sem):
    V = {v["venue"]: v for v in venues}
    semI = (sem == "I")
    flags = []
    def push(t, d, sev): flags.append({"type": t, "detail": d, "severity": sev})
    # R1
    blk = defaultdict(list)
    for s in sessions:
        blk[(s.get("prog"), s.get("nta"), s.get("stream"), s.get("mod"), s.get("code"))].append(s)
    for k, v in blk.items():
        days = {x["day"] for x in v}
        if len(v) != 2:
            push("R1_SESSION_COUNT", f"{k[0]} {k[3]} (str {k[2]}): {len(v)} sessions/week (expected 2)", "review" if semI else "hard")
        elif len(days) < 2:
            push("R1_SAME_DAY", f"{k[0]} {k[3]} (str {k[2]}): both sessions on {list(days)[0]}", "review" if semI else "hard")
    ic = defaultdict(int)
    for s in sessions:
        if s.get("instr"): ic[(s["instr"], s["day"], s["t"])] += 1
    for k, c in ic.items():
        if c > 1: push("R3_INSTRUCTOR_CLASH", f"{k[0]} double-booked {k[1]} @{k[2]}:00 ({c}x)", "hard")
    cc = defaultdict(int)
    for s in sessions:
        cc[(s.get("prog"), s.get("nta"), s.get("stream"), s["day"], s["t"])] += 1
    for k, c in cc.items():
        if c > 1: push("R4_COHORT_CLASH", f"{k[0]} {k[1]} (str {k[2]}) double-booked {k[3]} @{k[4]}:00", "review" if semI else "hard")
    for s in sessions:
        v = V.get(s["venue"])
        if v and s["occ"] > v["capacity"] + TOL:
            push("R5_OVER_CAPACITY", f"{s['venue']} [{v['capacity']}] holds {s['occ']} ({s.get('prog')} {s.get('mod')}, {s['day']} {s.get('time')})", "hard")
        if v and v["premises"] == "Saba" and s["t"] in EVE:
            push("R6_SABA_EVENING", f"{s['venue']} at {s.get('time')} ({s.get('prog')} {s.get('mod')}) — Saba ends 17:00", "hard")
        if v and v["is_lab"] and not is_it(s):
            push("R7_LAB_NON_IT", f"{s['venue']} (lab) used for non-IT '{s.get('mod')}' ({s.get('prog')}, {s['day']} {s.get('time')})", "hard")
        if "NTA9" in (s.get("nta") or ""):
            if s["venue"] not in ("BTA", "BTB", "BTC"):
                push("R8_NTA9_VENUE", f"NTA9 {s.get('mod')} in {s['venue']} (must be BTA/BTB/BTC) — {s['day']} {s.get('time')}", "hard")
            if not (s["t"] in EVE or s["day"] == "Sat"):
                push("R8_NTA9_TIME", f"NTA9 {s.get('mod')} at {s['day']} {s.get('time')} (must be evening/Saturday)", "hard")
            inf = instructors.get(s.get("instr"))
            if inf and inf.get("matched") and not inf.get("is_phd"):
                push("R9_NTA9_NON_PHD", f"NTA9 {s.get('mod')} assigned to {s.get('instr')} (not recorded PhD)", "review")
        if prog_is_it(s):
            inf = instructors.get(s.get("instr"))
            if inf and inf.get("matched") and inf.get("dept") and inf["dept"] != "Ict & Mathematics":
                push("R9_IT_NON_ICT", f"IT-programme '{s.get('mod')}' assigned to {s.get('instr')} ({inf['dept']})", "review")
    # workload
    wl = {}
    for s in sessions:
        n = s.get("instr")
        if not n: continue
        w = wl.setdefault(n, {"mods": set(), "day": 0, "eve": 0})
        w["mods"].add((s.get("mod"), s.get("code")))
        if s["t"] in EVE: w["eve"] += 2
        else: w["day"] += 2
    workload = []
    for n, w in wl.items():
        nm, dh, eh, fl = len(w["mods"]), w["day"], w["eve"], []
        if nm > 7: fl.append("MODULES>7")
        elif nm >= 6: fl.append("modules>=6")
        if dh > 32: fl.append("DAYTIME>32h")
        elif dh >= 28: fl.append("daytime>=28h")
        if eh > 20: fl.append("EVENING>20h")
        elif eh >= 16: fl.append("evening>=16h")
        inf = instructors.get(n, {})
        workload.append({"instructor": n, "dept": inf.get("dept"), "qual": inf.get("qual"), "is_phd": inf.get("is_phd", False),
                         "matched": inf.get("matched", False), "modules": nm, "daytime_h": dh, "evening_h": eh,
                         "total_h": dh + eh, "flags": fl})
    workload.sort(key=lambda w: -w["total_h"])
    for w in workload:
        for f in w["flags"]:
            if f.isupper() and f != f.lower():
                push("INSTRUCTOR_OVERLOAD", f"{w['instructor']}: {w['modules']} modules, {w['daytime_h']}h day, {w['evening_h']}h eve — {f}", "hard")
    # vutil
    vutil = []
    for v in venues:
        used = sum(1 for s in sessions if s["venue"] == v["venue"])
        avail = 6 * (5 if v["premises"] == "Saba" else 7)
        seat = sum(s["occ"] for s in sessions if s["venue"] == v["venue"])
        vutil.append({"venue": v["venue"], "capacity": v["capacity"], "premises": v["premises"], "type": v["type"],
                      "periods_used": used, "periods_avail": avail, "seat_periods_used": seat,
                      "utilisation": round(100 * used / avail, 1) if avail else 0})
    # metrics
    used = {(s["venue"], s["day"], s["t"]) for s in sessions}
    avail = sum(6 * (5 if v["premises"] == "Saba" else 7) for v in venues)
    peak = 0
    for d in DAYS:
        for t in STARTS:
            u = sum(1 for s in sessions if s["day"] == d and s["t"] == t)
            av = sum(1 for v in venues if not (v["premises"] == "Saba" and t in EVE))
            peak = max(peak, 100 * u / av if av else 0)
    over = [w for w in workload if any(f.isupper() and f != f.lower() for f in w["flags"])]
    soft = [w for w in workload if w["flags"] and w not in over]
    metrics = {"sessions": len(sessions), "venues": len(venues), "seatcap": sum(v["capacity"] for v in venues),
               "avail": avail, "used": len(used), "vacant": avail - len(used),
               "util": round(100 * len(used) / avail, 1) if avail else 0, "peak": round(peak, 1),
               "instructors": len({s["instr"] for s in sessions if s.get("instr")}),
               "modules": len({(s.get("mod"), s.get("code")) for s in sessions}),
               "overloads": len(over), "softs": len(soft),
               "hard": sum(1 for f in flags if f["severity"] == "hard"),
               "review": sum(1 for f in flags if f["severity"] == "review"),
               "estimated": all(s.get("est") for s in sessions) if sessions else False}
    return {"workload": workload, "vutil": vutil, "flags": flags, "metrics": metrics}
