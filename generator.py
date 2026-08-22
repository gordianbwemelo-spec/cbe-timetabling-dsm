"""Timetable generator for the CBE system.
From the reference data (enrolment, venues, curriculum, teaching capability, staff)
it sizes streams, allocates venues and instructors under the rules and load caps,
and red-flags anything that cannot be placed or staffed. Greedy, deterministic."""
import math
from collections import defaultdict
import rules

DAY_T = [7, 9, 11, 13, 15]
EVE_T = [17, 19]
EVE = set(EVE_T)

def time_of(t):
    return f"{t:02d}:00-{t+2:02d}:00"

def generate(sem, venues, instructors, teaching, curriculum, enrolment, settings):
    def sget(k, d):
        try:
            return int(settings.get(k, d))
        except (TypeError, ValueError):
            return d
    tol = sget("seat_tolerance", 10)
    # Stream size depends on the ACTUAL venue capacity (largest usable room),
    # optionally capped by a manual "max_stream_size" if the user set a number.
    _halls = [v["capacity"] for v in venues if not v["is_lab"]]
    largest_hall = max(_halls) if _halls else 100
    _pg = [v["capacity"] for v in venues if v["venue"] in ("BTA", "BTB", "BTC")]
    largest_pg = max(_pg) if _pg else 56
    try:
        user_cap = int(settings.get("max_stream_size"))
    except (TypeError, ValueError):
        user_cap = 0  # "auto" / blank => no manual cap; use the room capacity
    cap_mod = sget("module_cap", 7)
    cap_day = sget("daytime_cap", 32)
    cap_eve = sget("evening_cap", 20)
    DAYS = [d.strip() for d in (settings.get("days") or "Mon,Tue,Wed,Thu,Fri,Sat").split(",") if d.strip()]

    V = list(venues)
    # teaching capability lookup (by module name and by code)
    can = defaultdict(set)
    for t in teaching:
        n = t.get("instructor")
        if not n:
            continue
        if t.get("module"):
            can[("m", t["module"].strip().lower())].add(n)
        if t.get("code"):
            can[("c", t["code"].strip().lower())].add(n)
    enr = {}
    for e in enrolment:
        try:
            enr[(e["programme"], e["nta"])] = int(e["total"])
        except (TypeError, ValueError):
            enr[(e["programme"], e["nta"])] = 0
    cur = defaultdict(list)
    for c in curriculum:
        cur[(c["programme"], c["nta"])].append(c)

    vbusy, ibusy, sbusy = set(), set(), set()
    iday, ieve, imod = defaultdict(int), defaultdict(int), defaultdict(set)
    sessions, flags = [], []
    stats = {"cohorts": 0, "streams": 0, "modules": 0, "sessions_needed": 0, "sessions_placed": 0}

    def is_it(nta, mod, code):
        return rules.is_it({"prog": "", "nta": nta, "mod": mod, "code": code})

    def venue_ok(v, size, nta, mod, code, t):
        if size > v["capacity"] + tol:
            return False
        if v["premises"] == "Saba" and t in EVE:
            return False
        if v["is_lab"] and not is_it(nta, mod, code):
            return False
        if "NTA9" in (nta or "") and v["venue"] not in ("BTA", "BTB", "BTC"):
            return False
        return True

    def eligible(nta, mod, code):
        s = set(can.get(("m", (mod or "").strip().lower()), set())) | set(can.get(("c", (code or "").strip().lower()), set()))
        out = []
        for n in s:
            inf = instructors.get(n, {})
            if "NTA9" in (nta or "") and not inf.get("is_phd"):
                continue
            out.append(n)
        return out

    for (prog, nta), mods in sorted(cur.items()):
        stats["cohorts"] += 1
        T = enr.get((prog, nta), 0)
        if T <= 0:
            flags.append({"type": "NO_ENROLMENT", "detail": f"{prog} {nta}: no enrolment figure — cannot size streams.", "severity": "review"})
            T = largest_hall  # assume one full stream so a schedule is still attempted
        nta9 = "NTA9" in (nta or "")
        # the biggest room this cohort could actually use decides the stream size
        room_max = largest_pg if nta9 else largest_hall
        target = room_max if user_cap <= 0 else min(user_cap, room_max)
        target = max(1, target)
        nstreams = max(1, math.ceil(T / target))
        size = math.ceil(T / nstreams)
        stats["streams"] += nstreams
        periods = EVE_T if nta9 else (DAY_T + EVE_T)
        for si in range(nstreams):
            stream = chr(65 + si) if nstreams > 1 else "A"
            for c in mods:
                mod, code = c.get("module", ""), c.get("code", "")
                stats["modules"] += 1
                stats["sessions_needed"] += 2
                mkey = (mod, code)
                cand = eligible(nta, mod, code)
                cand.sort(key=lambda n: iday[n] + ieve[n])
                done = False
                for instr in cand:
                    new_mod = mkey not in imod[instr]
                    if new_mod and len(imod[instr]) >= cap_mod:
                        continue
                    placed = []
                    used_days = set()
                    for day in sorted(DAYS, key=lambda d: sum(1 for (p, n, s2, dd, tt) in sbusy if (p, n, s2) == (prog, nta, stream) and dd == d)):
                        if len(placed) == 2:
                            break
                        if day in used_days:
                            continue
                        for t in periods:
                            if nta9 and not (t in EVE or day == "Sat"):
                                continue
                            if (instr, day, t) in ibusy:
                                continue
                            if (prog, nta, stream, day, t) in sbusy:
                                continue
                            if t in EVE and ieve[instr] + 2 > cap_eve:
                                continue
                            if t not in EVE and iday[instr] + 2 > cap_day:
                                continue
                            rooms = [v for v in V if (v["venue"], day, t) not in vbusy and venue_ok(v, size, nta, mod, code, t)]
                            if not rooms:
                                continue
                            rooms.sort(key=lambda v: v["capacity"])
                            v = rooms[0]
                            placed.append((day, t, v))
                            used_days.add(day)
                            break
                    if len(placed) == 2:
                        for (day, t, v) in placed:
                            vbusy.add((v["venue"], day, t))
                            ibusy.add((instr, day, t))
                            sbusy.add((prog, nta, stream, day, t))
                            if t in EVE:
                                ieve[instr] += 2
                            else:
                                iday[instr] += 2
                            sessions.append({"day": day, "t": t, "time": time_of(t), "venue": v["venue"], "cap": v["capacity"],
                                             "prog": prog, "nta": nta, "stream": stream, "mod": mod, "code": code,
                                             "instr": instr, "occ": size, "est": 1})
                        imod[instr].add(mkey)
                        stats["sessions_placed"] += 2
                        done = True
                        break
                if not done:
                    reason = "no capable/available instructor" if not cand else "no free room/slot within caps"
                    flags.append({"type": "UNPLACED", "detail": f"{prog} {nta} str {stream} — {mod}: {reason}.", "severity": "hard"})

    stats["sessions_flagged"] = stats["sessions_needed"] - stats["sessions_placed"]
    return {"sessions": sessions, "flags": flags, "stats": stats}
