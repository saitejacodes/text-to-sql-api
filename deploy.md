# Deploy to Render

Two services from one repo, defined in [`render.yaml`](render.yaml):

| Service | What | URL (if the name is free) |
|---|---|---|
| `asksql-api` | FastAPI backend, built from the `Dockerfile`, Singapore, paid instance (never sleeps) | `https://asksql-api.onrender.com` |
| `asksql-web` | React frontend, static site built from `web/` | `https://asksql-web.onrender.com` |

The demo databases are baked into the image read-only. The LLM key lives only in Render's
dashboard, never in git (`.env` is gitignored and excluded from the Docker build).

## 1. Push the code

```bash
cd ~/jb_best_resume/text-to-sql-api && git push origin main
```

## 2. Create a fresh Groq key

console.groq.com/keys → **Create API key**. Delete any key that was ever pasted into a chat.
Keep the new one open in that tab; you paste it in step 3 and nowhere else.

## 3. Create the Blueprint

1. dashboard.render.com → **New** → **Blueprint**.
2. Connect GitHub and pick `saitejacodes/text-to-sql-api`, branch `main`.
3. Render reads `render.yaml` and asks for the three `sync: false` values:

| Key | Service | Value |
|---|---|---|
| `T2SQL_LLM_API_KEY` | asksql-api | your new Groq key |
| `T2SQL_ALLOWED_ORIGINS` | asksql-api | `https://asksql-web.onrender.com` |
| `VITE_API_URL` | asksql-web | `https://asksql-api.onrender.com` |

4. **Apply**. The API build takes ~3–5 minutes (Docker), the website ~1 minute.

## 4. If Render gave different URLs

Names are global; if `asksql-api` was taken, Render adds a suffix (e.g. `asksql-api-x7k2`).
Check each service's URL at the top of its page, then:

- `asksql-api` → **Environment** → set `T2SQL_ALLOWED_ORIGINS` to the website's real URL → **Save, rebuild, and deploy**.
- `asksql-web` → **Environment** → set `VITE_API_URL` to the API's real URL → **Save, rebuild, and deploy**
  (Vite bakes this into the build, so the site must rebuild).

## 5. Smoke test

```bash
curl -s https://asksql-api.onrender.com/health
```

Expect `{"status":"ok", ... "commit":"<git sha>", "model":"qwen/qwen3.8-27b"}`.

```bash
curl -s https://asksql-api.onrender.com/api/query -H 'content-type: application/json' -d '{"db_id":"university","question":"Which instructors teach in the Stata Center?"}'
```

Expect `"status":"ok"` with two rows (Turing, Torvalds).

Then open the website on your laptop **and** your phone:

1. Click an example → you see SQL, a green "Passed security sandbox" badge and a table.
2. Click **"Delete all students who enrolled before 2023"** → red **Blocked** badge.
3. The About page loads (refreshing `/about` must work too; that's the rewrite rule).

## Costs and limits

- `asksql-api` uses Render's default paid instance; the $50 credit covers it for months.
  The static site is free. Render → **Billing** shows usage.
- Groq free tier (measured 26 Oct 2026): 8,000 tokens/minute, 1,000 requests/day. One new
  question ≈ 6,400 tokens, so about one new question per minute. Repeated questions are served
  from the response cache (no tokens). The cache resets on each deploy.

## Logs and metrics

- Render → `asksql-api` → **Logs**: one JSON line per request; questions appear only as length + hash.
- `https://asksql-api.onrender.com/metrics`: Prometheus metrics (`t2sql_query_total`,
  `t2sql_sandbox_blocks_total`, `t2sql_query_latency_seconds`, ...).
