# CBE Timetabling System

A shared, multi-device timetabling application for the College of Business Education
(Dar es Salaam Campus). It is a real client–server program — a Python web server with a
central database — not a static file. One person runs it; **everyone else opens it in a web
browser on any device** (phone, tablet, laptop) and sees the same, always-up-to-date timetable.

It covers **Semester I and Semester II**, lets staff **browse, add, edit and delete** sessions,
and **checks every change against the timetabling rules**, warning before anything that breaks a
rule is saved (you can override; overrides show up on the Red-flags page). Workload and all
dashboard totals are read directly from the timetable, so they always agree.

---

## What's inside

| Tab | Shows |
|-----|-------|
| Overview | Dashboard totals, busiest venues, highest instructor loads |
| Timetable | Day grid of venue [capacity] × 7 periods, vacant periods shaded |
| Sessions | Searchable list — **add / edit / delete** with live rule-checking; export |
| Instructor TT | Each lecturer's weekly grid and load |
| Venue Dashboard | Utilisation per venue |
| Workload | Modules, daytime/evening/total hours per lecturer; caps flagged |
| Venue Capacity | Every venue and its seat capacity |
| Red-flags | Hard rule-breaks and items to review |

Rules enforced: two sessions per module/stream on different days (R1); same instructor both
sessions (R2); no instructor, cohort or room double-booked (R3, R4); room capacity +10 tolerance
(R5); Saba Saba ends 17:00 (R6); labs only for hands-on IT (R7); Master's/NTA9 evening-or-Saturday
in BTA/BTB/BTC (R8); appropriate allocation — PhD for Master's, ICT staff for IT (R9); and the
load limits — 7 modules, 32 daytime hours, 20 evening hours (soft 6 / 28 / 16).

---

## Option A — Run on one office PC, use from any device on the same Wi‑Fi

**You need:** Python 3.10 or newer (one-time install from <https://www.python.org/downloads/> —
tick *"Add Python to PATH"* on Windows).

1. Unzip this folder anywhere (e.g. Desktop).
2. **Windows:** double-click **`Start-Windows.bat`**.
   **Mac/Linux:** open Terminal in this folder and run `bash Start-Mac-Linux.sh`.
3. The first run sets itself up automatically (a minute or two). When ready it prints:

   ```
   On this computer:   http://localhost:5000
   On other devices:   http://192.168.x.x:5000   (same Wi-Fi/network)
   ```

4. On the **same PC**, open `http://localhost:5000`.
   On a **phone/tablet/another laptop** connected to the same Wi‑Fi, open the
   `http://192.168.x.x:5000` address shown (share it, or make a QR code of it).

Everyone is now editing one shared timetable. Leave the window open while in use; close it (or
press Ctrl+C) to stop. All data is saved in `timetable.db` in this folder.

> If other devices can't connect, allow Python through the Windows Firewall when first prompted
> (Private networks), or add an inbound rule for the port (5000).

---

## Option B — Put it on the internet (any device, anywhere) — free

Use a free host so people can reach it from any network via a normal web link.

**Render.com (free):**
1. Put this folder in a GitHub repository.
2. On <https://render.com> → **New → Blueprint** → select the repo. It reads `render.yaml`
   and deploys automatically, giving you a URL like `https://cbe-timetabling.onrender.com`.
3. Share that link — it works on any device, anywhere.

Also works on Railway, Fly.io, PythonAnywhere, or any host that runs a `Procfile`/Docker image.

**Docker (any server):**
```bash
docker compose up -d      # then open http://<server-ip>:5000
```

> On free cloud tiers the app may sleep when idle and take ~30s to wake. The included
> `render.yaml`/`docker-compose.yml` attach a persistent disk so your edits are kept.

---

## Changing the timetable data (new semester / new year)

The published timetables are seeded from **`seed_data.json`**. To load a new set of data,
replace that file (same structure) and delete `timetable.db`, then start the app — it re-seeds.
The **"Reset to published"** button on the Sessions tab restores a semester to the seed at any time.

## Backing up
Copy `timetable.db` — that single file is your entire live timetable, including all edits.

## Notes
- Occupancy in Semester I is an estimate (the source foundation timetable has no per-class counts);
  Semester II carries real class sizes. This is labelled in the app.
- Instructor department/qualification is known for lecturers whose names matched the academic-staff
  list; the PhD/ICT allocation checks apply to those. Clash, capacity and load checks apply to all.

---
*Built for the Quality Assurance Unit's proposed timetabling model: streams sized to rooms,
workload read from the finished timetable, rules enforced automatically, one dataset behind both
the web app and the Excel exports.*
