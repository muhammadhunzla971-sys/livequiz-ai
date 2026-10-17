# Deployment (free tier friendly)

Backend + Postgres + Redis on **Render**, frontend on **Vercel**. Total time: about 20 minutes.
Free plans sleep when idle (first request after a break takes ~30 s) and the free Render Postgres
expires after a while. That is fine for a demo; use paid plans for real classes.

## 1. Put the code on GitHub
Push the whole project (the folder that contains `backend/`, `frontend/`, `render.yaml`).
Never commit `.env` (it is already in `.gitignore`).

## 2. Backend on Render
1. Render dashboard → **New** → **Blueprint** → pick your GitHub repo. It reads `render.yaml` and
   creates the API, Postgres and Redis (Key Value).
2. After the first deploy open the **livequiz-api** service → **Environment** and fill in:
   - `LLM_API_KEY` = your Groq key
   - `FRONTEND_URL` = your Vercel URL (step 3), e.g. `https://livequiz-ai.vercel.app`
   - `CORS_ORIGINS` = the same URL (no trailing slash)
3. Save. Render redeploys. Open `https://<your-api>.onrender.com/ready`: it must show
   `{"postgres":"ok","redis":"ok"}`.

The container runs the database migrations on every start, so there is nothing else to do.
In production (`ENV=prod`) the API **refuses to start** if `JWT_SECRET` is a default value or CORS is
`*`, so a bad config fails loudly instead of running insecurely.

## 3. Frontend on Vercel
1. Vercel → **Add New Project** → same GitHub repo → **Root Directory: `frontend`**.
2. Environment variable: `VITE_API_URL` = `https://<your-api>.onrender.com` (no trailing slash).
3. Deploy. Copy the Vercel URL into `FRONTEND_URL` and `CORS_ORIGINS` on Render (step 2.2).

WebSockets connect straight to the backend (Vercel cannot proxy them), which is why
`VITE_API_URL` is needed.

## 4. Check it works
1. Open the Vercel URL → sign up → create a quiz with AI → Launch live.
2. Join from your phone with the PIN.
3. Finish the game and open the report.

## Optional
- Demo data: Render service → **Shell** → `python -m app.seed` (demo teacher
  `demo@livequiz.ai`, password `demo-password-123`; change or delete it before real use).
- Monitoring: set `METRICS_TOKEN`, then scrape `GET /metrics` with `Authorization: Bearer <token>`.
- Other backend hosts (Railway, Fly): same Dockerfile (`backend/Dockerfile`); set `ENV=prod`,
  `TRUSTED_PROXY_HOPS=1`, `DATABASE_URL`, `REDIS_URL` and the variables above.
- Several API instances: supported (live events travel over Redis pub/sub); keep one Redis.

## Troubleshooting
| Symptom | Cause |
|---|---|
| Browser console: CORS error | `CORS_ORIGINS` does not match the Vercel URL exactly |
| Login works, live game never connects | `VITE_API_URL` missing or `http://` instead of `https://` |
| "AI generation is unavailable" | `LLM_API_KEY` empty/wrong, or model names changed: check `docker logs` / Render logs for `llm unavailable` |
| API crashes at start with "Unsafe production configuration" | read the message: it names the setting |
