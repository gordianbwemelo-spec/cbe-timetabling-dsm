"""Timetable generator for the CBE system.
From the reference data (enrolment, venues, curriculum, teaching capability, staff)
it sizes streams, allocates venues and instructors under the rules and load caps,
and red-flags anything that cannot be placed or staffed. Greedy, deterministic."""
import math, re
from collections import defaultdict
import rules

DAY_T = [7, 9, 11, 13, 15]
EVE_T = [17, 19]
EVE = set(EVE_T)

# Rooms an NTA9 (postgraduate) cohort may use.
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
    # Stream size depends on the ACTUAL venue capacity (largest usable room),
    # optionally capped by a manual "max_stream_size" if the user set a number.
    _halls = [v["capacity"] for v in venues if not v["is_lab"]]
    largest_hall = max(_halls) if _halls else 100
    _pg = [v["capacity"] for v in venues if _nta9_venue(v["venue"])]
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
    def _lvl(x):
        m = re.search(r"(\d)", x or "")
        return m.group(1) if m else None
    # capability: module/code -> list of (instructor, level-they-may-teach or None=any)
    can = defaultdict(list)
    for t in teaching:
        n = t.get("instructor")
        if not n:
            continue
        tl = _lvl(t.get("nta"))
        if t.get("module"):
            can[("m", t["module"].strip().lower())].append((n, tl))
        if t.get("code"):
            can[("c", t["code"].strip().lower())].append((n, tl))
    enr = {}       # daytime / full-time headcount
    enr_eve = {}   # evening-and-weekend-only headcount
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
        cands = list(can.get(("m", (mod or "").strip().lower()), [])) + list(can.get(("c", (code or "").strip().lower()), []))
        out = []
        for n, tl in cands:
            if n in out:
                continue
            # NTA legitimacy: if the capability names a level, it must match the session's level
            if tl and slvl and tl != slvl:
                continue
            inf = instructors.get(n, {})
            if (inf.get("status") or "On duty") == "Study leave":
                continue  # not on duty — cannot be allocated
            if "NTA9" in (nta or "") and not inf.get("is_phd"):
                continue
            out.append(n)
        return out

    for (prog, nta), mods in sorted(cur.items()):
        stats["cohorts"] += 1
        nta9 = "NTA9" in (nta or "")
        day_ct = enr.get((prog, nta), 0)
        eve_ct = enr_eve.get((prog, nta), 0)
        # Split into sub-cohorts: (stream suffix, headcount, evening-only?).
        # Full-time daytime students have no time restriction. Evening/weekend
        # students (and all of NTA9) may only sit Mon-Fri 17:00-21:00 or Sat 07:00-21:00.
        subs = []
        if nta9:
            subs.append(("", (day_ct + eve_ct), True))
        else:
            if day_ct > 0:
                subs.append(("", day_ct, False))
            if eve_ct > 0:
                subs.append(("-E", eve_ct, True))
            if day_ct <= 0 and eve_ct <= 0:
                flags.append({"type": "NO_ENROLMENT", "detail": f"{prog} {nta}: no enrolment figure — cannot size streams.", "severity": "review"})
                subs.append(("", largest_hall, False))
        room_max = largest_pg if nta9 else largest_hall
        target = room_max if user_cap <= 0 else min(user_cap, room_max)
        target = max(1, target)
        for (suffix, headcount, evening) in subs:
            nstreams = max(1, math.ceil(headcount / target))
            size = math.ceil(headcount / nstreams)
            stats["streams"] += nstreams
            for si in range(nstreams):
                stream = (chr(65 + si) if nstreams > 1 else "A") + suffix
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
                        if new_mod and len(imod[instr]) >= mod_limit(instr):
                            continue  # respects part-time / volunteer module limits
                        adays, apers = avail(instr)
                        placed = []
                        used_days = set()
                        for day in sorted(DAYS, key=lambda d: sum(1 for (p, n, s2, dd, tt) in sbusy if (p, n, s2) == (prog, nta, stream) and dd == d)):
                            if len(placed) == 2:
                                break
                            if day in used_days:
                                continue
                            if adays and day not in adays:
                                continue  # instructor not available this day
                            for t in (DAY_T + EVE_T):
                                if evening and not (day == "Sat" or t in EVE):
                                    continue  # evening cohort: weekday evenings only, Saturday all day
                                if apers and t not in apers:
                                    continue  # instructor not available this period
                                if (instr, day, t) in ibusy:
                                    continue
                                if (prog, nta, stream, day, t) in sbusy:
                                    continue
                                day_ts = [tt for (p, n, s2, dd, tt) in sbusy if (p, n, s2, dd) == (prog, nta, stream, day)]
                                if rules.max_consecutive(day_ts + [t]) > rules.MAX_CONSEC:
                                    continue  # would exceed 3 back-to-back sessions for this stream
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
                        if not cand:
                            ftype, reason = "NO_CAPABLE_STAFF", "no qualified, on-duty lecturer can teach this — add teaching capability or a part-timer"
                        elif all((len(imod[n]) >= mod_limit(n)) or (iday[n] >= cap_day and ieve[n] >= cap_eve) for n in cand):
                            ftype, reason = "PART_TIMER_NEEDED", "all qualified lecturers are at capacity — a PART-TIMER is needed"
                        else:
                            ftype, reason = "UNPLACED", "no free room/time slot within the rules"
                        flags.append({"type": ftype, "detail": f"{prog} {nta} str {stream} — {mod}: {reason}.", "severity": "hard"})

    stats["sessions_flagged"] = stats["sessions_needed"] - stats["sessions_placed"]
    return {"sessions": sessions, "flags": flags, "stats": stats}
