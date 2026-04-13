# Mangarr

Mangarr is a Sonarr/Radarr-style manga manager focused on:

- library classification (scan + match)
- organizing and renaming manga files
- clear, Arr-inspired UI workflows

Downloading is intentionally out of scope for the current MVP.

## Stack

- Backend: FastAPI + SQLAlchemy + SQLite
- Frontend: React + Vite + TypeScript
- Containers: Docker + Docker Compose

## Local Development (Hot Reload)

### Backend

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Open:

- UI: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`

## Docker (Unified Image)

```bash
docker compose up --build -d
```

The unified container image stores runtime data under **`/config`** (SQLite at **`/config/mangarr.db`**, covers next to it). No Compose environment variables are required.

If you want persistence across container recreation, bind-mount a host folder to `/config` (optional), for example:

```yaml
volumes:
  - /your/host/path:/config
```

Open:

- UI + API: `http://localhost:8000`

Stop:

```bash
docker compose down
```

The workflow uses `GITHUB_TOKEN`; no extra secrets are required for publishing to the same repository namespace.
