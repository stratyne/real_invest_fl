# Project Penstock - context/local_dev.md
# Local development environment setup and operational procedures.
# Last updated: 2026-06-02

## Environment

| Component | Value |
|---|---|
| Repo root | D:\Chris\Documents\Stratyne\real_invest_fl |
| Python venv | .venv |
| Frontend | frontend/ (Vite + React) |
| API local port | 8001 |
| Vite dev port | 3000 |
| DB container | real_invest_db (localhost:5432) |
| Swagger UI | http://127.0.0.1:8001/docs |

## Local Dev - API

    cd D:\Chris\Documents\Stratyne\real_invest_fl
    .venv\Scripts\Activate.ps1
    uvicorn real_invest_fl.api.main:app --reload

API available at http://127.0.0.1:8001. Swagger UI at http://127.0.0.1:8001/docs.

## Local Dev - Frontend

    cd D:\Chris\Documents\Stratyne\real_invest_fl\frontend
    npm run dev

Frontend available at http://localhost:3000. Vite proxies API requests to
http://127.0.0.1:8001 - both must be running simultaneously for the full
UI to function.

## Deployment - Staging to Production

Run after any frontend or backend change:

    git pull
    docker compose build nginx app
    docker compose up -d

No volume management required. Frontend static files are built directly
into the Nginx image via multi-stage Dockerfile.

## Machine Reboot SOP

    # 1. Start Docker Desktop and wait for engine ready, then:
    cd D:\Chris\Documents\Stratyne\real_invest_fl

    # 2. Verify containers - restart: unless-stopped means they may already
    #    be running after Docker engine start.
    docker compose ps

    # 3. If any container is not running:
    docker compose up -d

## DB Verification Pattern

All DB queries from the host use this pattern:

    docker exec -it real_invest_db psql -U penstock -d real_invest_fl -c "<query>"

## Notes

- Scripts that run on the Windows host (nal_ingest.py, gis_ingest.py,
  CAMA scrapers, batch scripts) use settings.host_database_url
  (localhost:5432). Never settings.database_url - that uses the Docker
  service name 'db' which is unreachable from the host.
- The .venv must be activated before running any host-side Python script.
- Docker Desktop must be running before any docker compose or
  docker exec command.
