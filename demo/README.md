# desto — Vercel demo

A self-contained, interactive **demo showcase** of the desto dashboard, built to run on
[Vercel](https://vercel.com)'s free **Hobby** plan.

> [!NOTE]
> This is a *static, read-only recreation* of the desto UI. All sessions, stats and logs
> are **simulated in your browser** — nothing runs on a server. The real desto manages live
> `tmux` sessions on your own machine; see the [main README](../README.md) to run it for real.

## Why a demo instead of the live app?

desto is a [NiceGUI](https://nicegui.io) (Python) server that:

- spawns and controls **`tmux`** sessions (real OS processes),
- pushes live updates to the browser over a **long-lived websocket**,
- and stores session state in **Redis**.

Vercel's Hobby plan only runs **short-lived, stateless serverless functions** — it can't keep a
process alive, can't run `tmux`, and can't hold a websocket open. So a genuine working instance
isn't possible there (that's why the full app is deployed on a container host like Render).

What *does* work on Hobby, with zero backend, is a single static page that faithfully reproduces
the dashboard and lets visitors click through it. That's what lives here: one `index.html` with
no build step and no dependencies.

## What's in the demo

- Pixel-faithful recreation of the Sessions Dashboard, light **and** dark mode.
- Live-updating system stats (CPU / memory / disk / tmux).
- A **Launch** button that starts a simulated session — watch it run, tick its duration up, then
  finish (try `fail.sh` to see a failure with exit code 1).
- Script preview with syntax highlighting, Scripts / New Script / Favorites tabs, a chain queue,
  and a streaming system log.
- Kill / View Log / Clear actions, Refresh, Clear History, Clear Logs.

## Files

| File           | Purpose                                             |
| -------------- | --------------------------------------------------- |
| `index.html`   | The entire demo (HTML + CSS + JS, no dependencies). |
| `vercel.json`  | Static hosting config and basic security headers.   |

## Deploy it to Vercel (free Hobby plan)

You'll do this part — Vercel needs to connect to your own GitHub account. It takes ~2 minutes.

### Option A — Vercel dashboard (recommended)

1. Go to **https://vercel.com/new** and sign in with GitHub.
2. Click **Import** next to the `kalfasyan/desto` repository.
   (If you don't see it, click *Adjust GitHub App Permissions* and grant access to the repo.)
3. On the configuration screen:
   - **Root Directory** → click *Edit* and choose **`demo`**. ← the only required change
   - **Framework Preset** → leave as **Other**.
   - **Build Command** → leave empty.
   - **Output Directory** → leave empty.
4. Click **Deploy**. In a few seconds you'll get a public URL like
   `https://desto-demo.vercel.app`.

That's it. Every push to `main` will auto-redeploy the demo.

### Option B — Vercel CLI

```bash
npm i -g vercel
cd demo
vercel          # follow the prompts; accept the defaults
vercel --prod   # promote to your production URL
```

### Notes

- **Custom domain:** add one under *Project → Settings → Domains* (free on Hobby).
- **Keep it demo-only:** because the root directory is `demo/`, Vercel only ever serves this static
  page — it never tries to build or run the Python app.
- **Link it back:** once deployed, consider adding a "Live demo ↗" badge/link to the main README.
