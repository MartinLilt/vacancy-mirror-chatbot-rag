# Web — vacancy-mirror.com

Split into two independent sub-projects:

```
web/
├── frontend/   Next.js app — deployed to Vercel (vacancy-mirror.com)
└── api/        FastAPI app — deployed to backend server (api.vacancy-mirror.com)
```

## Architecture

```
[User browser]
     │
     ▼
vacancy-mirror.com  ──→  Vercel (Next.js)
                              │  fetch()
                              ▼
                    api.vacancy-mirror.com  ──→  Hetzner backend server
                              │                  (FastAPI + Stripe webhook)
                              ▼
                          PostgreSQL (same server)
```

## DNS setup (Cloudflare / your registrar)

| Record | Name                   | Value                |
| ------ | ---------------------- | -------------------- |
| A      | api.vacancy-mirror.com | 178.104.113.58       |
| CNAME  | vacancy-mirror.com     | cname.vercel-dns.com |

## Frontend (Next.js) — `web/frontend/`

- Framework: Next.js 14 (App Router)
- Deploy: Vercel (free tier)
- Env var: `NEXT_PUBLIC_API_URL=https://api.vacancy-mirror.com`

```bash
cd web/frontend
npm install
npm run dev        # http://localhost:3000
```

## API (FastAPI) — `web/api/`

- Framework: FastAPI + Uvicorn
- Deploy: Docker on Hetzner backend server, port 8000
- Nginx proxies `api.vacancy-mirror.com` → `localhost:8000`
- Stripe webhook endpoint: `POST /webhook`

```bash
cd web/api
pip install -e .
uvicorn app.main:app --reload  # http://localhost:8000
```
