# AI-Powered Predictive Logistics Maintenance

Predict equipment failures before they happen. This repository delivers a full-stack reference solution for logistics and warehouse operations that blends live telemetry ingestion, AI-driven risk scoring, alerting, and an operator-focused dashboard. It bundles a FastAPI backend, a modern React frontend, Google Generative AI integration, simulator tooling, and Docker workflows so you can demo, iterate, or extend it quickly.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Key Capabilities](#key-capabilities)
3. [System Requirements](#system-requirements)
4. [Configuration](#configuration)
5. [Running the Stack](#running-the-stack)
6. [Google Generative AI Integration](#google-generative-ai-integration)
7. [Data Flow & Workflows](#data-flow--workflows)
8. [Frontend Guide](#frontend-guide)
9. [Backend API Reference](#backend-api-reference)
10. [Simulator Tool](#simulator-tool)
11. [Testing](#testing)
12. [Troubleshooting](#troubleshooting)
13. [Roadmap Ideas](#roadmap-ideas)
14. [License](#license)

---

## Architecture Overview

```
+---------------+  REST/WebSocket  +----------------------+ 
| React / Vite  |<---------------->| FastAPI (uvicorn,    | 
| Frontend UI   |                  | SQLAlchemy, websocket| 
+-------+-------+                  +----------+-----------+ 
        | WebSocket feed                      |             
        v                                     v             
+---------------+      AI scoring      +------------------+ 
| Operations &  |<-------------------->| Google Generative| 
| Maintenance   |                     | AI (Gemini REST) | 
+---------------+                     +------------------+ 
        ^                                     |             
        | REST API                            |             
        |                                     v             
+---------------+   Data persistence   +------------------+ 
| Simulator CLI |--------------------->| SQLite (default) | 
| Sensor input  |                     | or Postgres      | 
+---------------+                     +------------------+ 
```

* **Backend**: FastAPI, SQLAlchemy ORM, JWT-ready security, WebSocket broadcaster, and ML service with local fallback + optional external providers.
* **Frontend**: React 18 (Vite) with Recharts visualizations, responsive layout, and Google AI what-if control.
* **AI Provider**: choose between built-in heuristic model, external HTTP service, or Google Generative AI (Gemini).
* **Packaging**: Docker Compose for dev (hot reload) and production (Nginx-hosted static build), plus a Python simulator to stream synthetic readings.

---

## Key Capabilities

- Asset monitoring: seeded devices (conveyor, forklift, truck) showcase the flow; extend via API or UI forms.
- Telemetry ingestion: REST endpoint (`POST /readings/`) stores sensor payloads, updates rolling metrics, and pushes WebSocket notifications.
- AI risk scoring:
  - Local heuristic / bundled RandomForest (joblib) for offline scenarios.
  - External HTTP model fallback.
  - Google Generative Language API for production-grade risk probabilities.
- Alerting: threshold-based (temperature, configurable) and predictive alerts when probabilities exceed customizable targets.
- Dashboard UI: instant metrics, real-time charts, live feed, and AI-driven what-if analysis.
- AI operations co-pilot: Gemini-powered triage summaries, playbooks, prioritization, anomaly explanations, inventory tips, compliance narratives, and more available directly from the dashboard.
- Incident archive & maintenance feedback logging: assistant conversations and technician outcomes are stored, surfaced per asset, and ready for audits or post-mortems.
- Simulator: CLI tool generates realistic telemetry streams to showcase the system.
- Testing: pytest suite covering health checks, external fallback, insights endpoints, and what-if predictions.

---

## System Requirements

- Docker 24+ and Docker Compose v2 (preferred) or the ability to run Python 3.11 + Node 20 locally.
- Google Generative Language API key (if using the Gemini provider).
- Optional: PowerShell or Bash for the command examples below.

---

## Configuration

Create your environment file:

```
cp .env.example .env
```

Update the following fields as needed:

| Variable | Description |
|----------|-------------|
| `MODEL_PROVIDER` | `local`, `external`, or `google`. |
| `GOOGLE_GENAI_API_KEY` | Required when using Google Gemini. |
| `GOOGLE_GENAI_MODEL` | Defaults to `gemini-1.5-flash`. |
| `EXTERNAL_MODEL_URL` / `EXTERNAL_MODEL_API_KEY` | Configure if using an external provider. |
| `ALERT_PROB_THRESHOLD` | Probability above which predictive alerts fire. |
| `ALERT_TEMPERATURE_MAX` | Threshold for temperature-based alerts. |
| `CORS_ORIGINS` | Allowed frontend origins (dev + prod already included). |
| `DB_URI` | Replace with PostgreSQL if needed (for example `postgresql+psycopg2://...`). |
| `CMMS_WEBHOOK_URL` / `CMMS_WEBHOOK_TOKEN` | Optional webhook invoked when predictive alerts fire; connect to CMMS or ticketing tools. |

Whenever `.env` changes, restart the backend container with `docker compose down` followed by `docker compose up --build` so the new configuration is applied.

---

## Running the Stack

### Developer Mode (hot reload)

```
docker compose down
docker compose up --build
```

- Backend: http://localhost:8000 (REST + WebSocket)
- Frontend: http://localhost:5173 (Vite dev server)
- Config check: `Invoke-RestMethod http://localhost:8000/insights/config`

### Production Mode (Nginx + optimized build)

```
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:8080 (Nginx serving the Vite build)
- Override build-time API URL: `VITE_API_URL=https://api.example.com docker compose -f docker-compose.prod.yml build`

Both stacks mount the source directories, so local edits (Python or React) hot reload in dev mode. In prod mode you must rebuild to pick up frontend changes.

---

## Google Generative AI Integration

1. Enable the Generative Language API in your Google Cloud project.
2. Add your key to `.env`:
   ```
   MODEL_PROVIDER=google
   GOOGLE_GENAI_API_KEY=AIza...your-key...
   GOOGLE_GENAI_MODEL=gemini-1.5-flash
   ```
3. Restart the stack so the backend reads the new settings.
4. Verify with `Invoke-RestMethod http://localhost:8000/insights/config | ConvertTo-Json -Depth 4` - it should report `provider: google` and `configured: true` in the `google` block.
5. Use the "What-If (Google AI)" panel in the dashboard to preview probabilities before committing real readings.

If the external call fails (network, quota, etc.), the backend automatically falls back to the local heuristic model so operations continue uninterrupted.

---

## Data Flow & Workflows

### 1. Telemetry ingestion

- Endpoint: `POST /readings/`
- Sample payload:
  ```json
  {
    "device_id": 1,
    "timestamp": "2025-01-01T00:00:00Z",
    "vibration": 2.4,
    "temperature": 62,
    "current": 11,
    "rpm": 1480,
    "load_pct": 70
  }
  ```
- Side effects:
  - Persists the reading.
  - Runs threshold checks (for example temperature).
  - Executes predictive model; stores probability.
  - Raises alerts when thresholds or probability rules trigger.
  - Broadcasts WebSocket events for live dashboards.
- Edge staging: intermittently connected assets can flush buffered readings via `POST /readings/batch`.

### 2. Alerting & predictions

- Thresholds come from `.env` (`ALERT_TEMPERATURE_MAX`, `ALERT_PROB_THRESHOLD`).
- `prob_to_severity` converts model output to low / medium / high.
- Predictive alerts include textual messages and feed events.
- Optional CMMS webhook publishes predictive alerts to downstream maintenance tools when `CMMS_WEBHOOK_URL` is set.

### 3. Dashboard experience

- Metrics card uses `/insights/metrics` for asset count, active alerts, readings (24h), high-risk count.
- Device selector fetches history via `/devices/{id}/readings?limit=60`.
- Recharts components visualize telemetry and risk trend.
- Live feed subscribes to `/readings/ws` for near-real-time updates.
- Role selector (manager / technician / dispatcher) reshapes the interface for strategic, field, or scheduling workflows.
- Assistant logs and maintenance feedback are surfaced so teams always see latest AI guidance and human actions.

### 4. What-if simulations

- Frontend sends a hypothetical reading to `/insights/what-if`.
- Backend appends the candidate to the device context, normalizes timestamps, and calls the chosen AI provider.
- Response returns a probability (0-1) without storing the reading.

---

## Frontend Guide

- Location: `frontend/`
- Stack: React 18, Vite 5, Recharts, date-fns.
- Styling: `src/styles.css` provides the dark neon theme.
- Entry point: `src/App.jsx` orchestrates metrics, charts, WebSocket feed, and what-if form.
- Role-aware layout: quick selector in the header toggles manager, technician, and dispatcher views.
- Operations co-pilot: submit scenarios, capture responses, and review the assistant history + maintenance feedback without leaving the dashboard.

### Development commands

```
cd frontend
npm install
npm run dev  # http://localhost:5173
```

### Production build within Docker

Handled automatically via `frontend/Dockerfile.prod` when using `docker-compose.prod.yml` (build stage -> Nginx runtime).

---

## Backend API Reference

| Method & Path | Description |
|---------------|-------------|
| `GET /health` | Readiness probe returning `{ "ok": true }`. |
| `POST /auth/register` | Create a new user (email, password, role). |
| `POST /auth/login` | Obtain a JWT token. |
| `GET /devices/` | List devices. |
| `POST /devices/` | Create a device. |
| `GET /devices/{id}/readings` | Fetch recent readings (limit 1-200). |
| `POST /readings/` | Ingest sensor data; triggers alerts + predictions. |
| `POST /readings/batch` | Edge staging endpoint to ingest an array of buffered readings. |
| `GET /readings/ws` | WebSocket endpoint for live readings/alerts. |
| `GET /insights/alerts` | Recent alerts (<= 200). |
| `GET /insights/predictions` | Recent predictions (<= 200). |
| `GET /insights/metrics` | Summary metrics for dashboard cards. |
| `GET /insights/config` | Server-side provider + thresholds. |
| `POST /insights/what-if` | AI probability query without persisting data. |
| `POST /insights/assistant` | Ask the AI co-pilot for triage summaries, playbooks, or planning help. |
| `GET /insights/assistant/logs` | Review logged assistant recommendations. |
| `POST /insights/feedback` / `GET /insights/feedback` | Record and list real maintenance outcomes per asset. |

---

## Simulator Tool

Located in `simulator/simulate.py`. Generates sample telemetry for a device.

```
cd simulator
python simulate.py --api http://localhost:8000 --device 1 --rate 2
```

- `--rate` controls seconds between readings.
- Adjust the script to simulate different sensor ranges.
- Useful for demos, load tests, or validating alert configurations.

---

## Testing

```
cd backend
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate.bat
pip install -r requirements.txt
pytest -q
```

Key tests include:
- `test_health.py`: health endpoint.
- `test_external_toggle.py`: ensures failure of external provider falls back to local model.
- `test_insights.py`: verifies metrics, history, and what-if probability pipeline end-to-end.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Frontend shows `Provider: LOCAL` | `.env` still has `MODEL_PROVIDER=local` or backend not restarted | Update `.env`, set `MODEL_PROVIDER=google`, supply `GOOGLE_GENAI_API_KEY`, then `docker compose down && docker compose up --build`. |
| `docker compose exec backend curl ...` fails | Backend image does not include `curl` | Use `Invoke-RestMethod` (PowerShell) or `docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read())"`. |
| 500 on `/insights/what-if` about timestamps | Mixed naive vs UTC timestamps | Fixed in `services/features.py`; rebuild containers if you pulled earlier images. |
| Backend container exits during startup with bcrypt error | Old bcrypt version incompatible with Passlib | Dependency pinned to `bcrypt==3.2.2`. Rebuild images to pick up the fix. |
| WebSocket feed empty | No readings yet | Send sample data via simulator or `POST /readings/`. |

---

## Roadmap Ideas

- Device management UI (create/edit devices with health status overrides).
- Alert acknowledgement workflow and role-based dashboards.
- Historical reporting exports (CSV, PDF).
- Multi-tenant support with organization scoping.
- Integration adapters for message brokers (Kafka, MQTT) in addition to REST.

---

## License

Licensed under the MIT License. See [`LICENSE`](LICENSE) for full text.

### Additional Recommendations

- **Automated incident archiving.** Persist AI co-pilot responses and human notes per asset so you can review how issues were triaged and resolved; great for audits and post-mortems.
- **Role-aware dashboards.** Add lightweight authentication in the frontend and tailor views (executive overview, technician details, dispatcher scheduling) based on the JWT role we already seed (manager/technician).
- **CMMS integration hooks.** Trigger webhook payloads or ticket creation whenever predictive alerts fire or the assistant produces actionable guidance, keeping maintenance planning systems in sync.
- **Edge data staging.** Allow forklifts, drones, or conveyors to buffer telemetry locally and push in batches when network connectivity is spotty, preventing gaps in analytics.
- **Automated feedback loop.** Capture actual repair outcomes and feed them back into the assistant prompts to refine recommendations and prioritize future work orders.

