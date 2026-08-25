# Ourex Personal OS

A calm, AI-native personal operating system command center. The UI is a responsive static application and the included Python service adds a small JSON API and event log.

## Run locally

```bash
python3 server.py
# http://localhost:8000
```

Or with a platform that reads `package.json`:

```bash
npm start
```

The app also has an offline-safe fallback state, so it renders correctly on static hosts such as GitHub Pages, Vercel static hosting, Netlify, or any CDN. API-backed persistence is enabled when served with `server.py`.

## Deploy

- **Render / Railway / Fly:** use `python3 server.py` as the start command. `Procfile` and `render.yaml` are included.
- **Static hosting:** publish the repository root. `index.html`, `styles.css`, and `app.js` are the complete browser bundle.
- **Port:** the server reads `PORT` and binds to `0.0.0.0`, making it compatible with hosted previews.

## Check

```bash
npm run check
```

See `ARCHITECTURE.md` for the Personal OS core boundaries and production expansion plan.
