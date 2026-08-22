# Putting the CBE Timetabling System online (get a web address)

This gives your system a permanent web address (e.g. `https://cbe-timetabling-dsm.onrender.com`)
that works on any device, anywhere — the same way your other systems are hosted on **Render**.

You'll do two things once: put the code on **GitHub**, then deploy it on **Render**.
Both have free accounts. Total time ~15 minutes.

---

## Step 1 — Put the code on GitHub

1. Create a free account at <https://github.com> (skip if you have one).
2. Click the **+** (top right) → **New repository**.
3. Name it e.g. `cbe-timetabling-dsm`, keep it **Private** if you prefer, click **Create repository**.
4. On the new repo page, click **“uploading an existing file”** (or **Add file → Upload files**).
5. Unzip this package on your computer, then **drag ALL the files and the `static` folder**
   from inside it into the upload area. Wait until they all appear.
6. Click **Commit changes**.

> Important: the files (`app.py`, `render.yaml`, `requirements.txt`, the `static` folder, etc.)
> must sit at the **top level** of the repository, not inside an extra sub-folder.

---

## Step 2 — Deploy on Render

1. Create a free account at <https://render.com> and click **Get Started** → sign in with GitHub
   (this lets Render see your repository).
2. In Render, click **New +** → **Blueprint**.
3. Choose your `cbe-timetabling-dsm` repository → **Connect**.
4. Render reads `render.yaml` and shows the service. Click **Apply** / **Create**.
5. Wait a few minutes while it builds. When it finishes, Render shows a **URL** at the top,
   like `https://cbe-timetabling-dsm.onrender.com`. **That is your web address** — open it on
   any device, share it with colleagues.

That's it. To update the system later, upload the changed files to the GitHub repo again and
Render redeploys automatically.

---

## Plan note (data safety)

- The included `render.yaml` uses Render's **Starter** plan with a small **persistent disk**, so
  all edits (timetable changes, corrections, uploaded data) are **kept** across restarts. Starter
  is a small monthly cost.
- To run **free** instead: open `render.yaml`, change `plan: starter` to `plan: free`, and delete
  the `disk:` and `envVars:` blocks (the file has a comment showing exactly this). On the free plan
  the app sleeps when idle and the database **resets on restart**, so you'd re-load data from the
  **Data** tab (CSV upload) after a reset. For a live, shared timetable, Starter is recommended.

## Backups
Whatever the plan, you can always export the current sessions from **Sessions → Export Excel/CSV**,
and reload reference data from the **Data** tab templates.
