# Product Comparison Agent

Agentic backend for a scalable product comparison website powered by Grok 4 Fast.  
The service orchestrates a six-step workflow that discovers comparison metrics, lifts products from authoritative review sites, extracts mandatory product data in parallel, generates comparisons, and formats the results for frontend consumption — all while respecting strict compute and API budgets.

## Project Structure

This repository contains both the backend and frontend:

- **`backend/`** - Python FastAPI backend with Grok 4 Fast integration
- **`frontend/`** - Next.js React frontend application

## Backend

### Key Capabilities
- Grok 4 Fast reasoning/non-reasoning modes with native search integration
- Hard-coded fallback discovery strategies for resilient product sourcing
- Parallel Step 4 extraction with concurrency/budget controls
- Aggressive Redis caching across metrics, product data, and comparisons
- Structured FastAPI endpoint returning ready-to-render payloads
- Centralized logging, error handling, and budget enforcement

### Project Layout
```
backend/
  agent/
    orchestrator.py   # Workflow coordinator
    prompts.py        # Prompt templates for each step
    steps.py          # Step implementations
  api/
    grok_client.py    # HTTP client wrapper with retries & timeouts
  cache/
    redis_cache.py    # Redis-backed cache helper
    logging_config.py   # structlog configuration utilities
    models/
      schemas.py        # Pydantic models for requests/responses
    infrastructure/
      __init__.py       # Exposes FastAPI app factory
      bootstrap.py      # Config, logging, metrics, Redis, API clients, background jobs
      auth.py           # AuthN/AuthZ, validation, rate limiting helpers
      middleware.py     # Endpoint wrapper, CORS, timeout utilities
      endpoints.py      # Public/admin routes and error handlers
      app.py            # FastAPI wiring and lifecycle hooks
config.py             # Environment-driven settings
main.py               # FastAPI application entry point
pyproject.toml        # Dependencies and tooling
```

### Running the Backend Locally
```bash
pip install -e .
uvicorn main:app --reload
```

The API exposes:
- `GET /api/health` – readiness probe
- `POST /api/compare` – body `{"category": "...", "constraints": "...optional..."}`  
  Returns `ComparisonResponse` containing metrics, formatted comparison payload, and workflow stats.

## Frontend

The frontend is a Next.js application located in the `frontend/` directory.

### Running the Frontend Locally
```bash
cd frontend
npm install
npm run dev
```

See `frontend/README.md` for more details.

## Infrastructure Package In Plain English

The files inside `backend/infrastructure/` work together as the "control tower" for the entire backend. In everyday language, they do the following:

- **Gets the house in order first.** It reads the environment settings, sets up logging, connects to Redis, and gets API clients ready so the rest of the code can depend on them.
- **Keeps track of what is happening.** It records metrics for Prometheus, logs every important event, and monitors the cost of serving each comparison request.
- **Checks who is knocking.** It validates API keys, enforces admin-only routes, applies rate limits, and stops suspicious input before it can cause problems.
- **Wraps every endpoint in safety gear.** The `endpoint_wrapper` decorator adds CORS headers, runs authentication, throttles traffic, times out slow handlers, logs results, and converts errors into friendly JSON responses.
- **Runs the main "compare products" request.** The `/api/v1/compare` endpoint cleans up the user's request, runs the full multi-step comparison workflow, and packages the answer for the frontend—all with the guardrails above.
- **Offers quick health updates.** The `/health`, `/ready`, and `/metrics` endpoints make it easy for load balancers and dashboards to know if the service is healthy.
- **Gives operators the tools they need.** Admin-only routes can clear product/query caches, fetch cache statistics, or trigger the scheduled price-refresh job on demand.
- **Starts the show.** The `create_app()` function wires everything into FastAPI, registers error handlers, and plugs in startup/shutdown hooks so background jobs and connections are opened and closed cleanly.

You can think of the file as a well-organised playbook: every helper builds towards keeping the main comparison experience reliable, observable, and safe.

## Delivery Status & Next Moves

- ✅ Infrastructure and HTTP layer are production-ready: configuration, logging, metrics, Redis, auth, rate limiting, comparison endpoint, admin utilities, and lifecycle hooks are all implemented and tested for syntax.
- 🔄 Remaining work:  
  - Write automated tests (unit + integration) to lock in behaviour and prevent regressions.  
  - Fill in any missing Redis maintenance functions backed by real data (e.g. product price index) and verify against staging data.  
  - Deploy to a staging environment, run load tests, and confirm observability dashboards (Prometheus, logs) capture the right signals.  
  - Update operational runbooks with the new admin endpoints and failure recovery steps.

## Sonar + Grok Workflow

1. **Sonar Agent A1 – Discovery & Validation**  
   Single prompt validates the request, produces comparison metrics, and returns exactly six candidate products. Results are cached by category.
2. **Sonar Agent B – Parallel Product Research**  
   Up to six Sonar agents run concurrently to gather pricing, links, summaries, pros/cons, and detailed reviews. Image search is executed as a dedicated Sonar step when needed. Outputs are cached per product per day.
3. **Grok Agent C – Ranking & Table Synthesis**  
   Grok 4 Fast Reasoning turns the research corpus into star ratings, rankings, and a comparison table ready for the frontend (with optional TL;DR text).

Compute budgets are enforced end-to-end (`MAX_TOTAL_SEARCHES`, `A1_SEARCH_BUDGET`, `B_SEARCH_BUDGET_PER_AGENT`, and `workflow_timeout≤32s`).

## Configuration

All settings are defined in `config.py` (Pydantic BaseSettings).  
Environment variables (with defaults) include:

- `GROK_API_KEY` / `GROK_BASE_URL`
- `PERPLEXITY_API_KEY` / `PERPLEXITY_BASE_URL` (Sonar)
- `SONAR_MODEL`, `SONAR_TIMEOUT_SECONDS`, `SONAR_MAX_RETRIES`
- `REDIS_URL`
- `MAX_API_CALLS_PER_COMPARISON`
- `WORKFLOW_TIMEOUT_SECONDS`, `STEP_TIMEOUT_SECONDS`
- `MAX_TOTAL_SEARCHES`, `A1_SEARCH_BUDGET`, `B_SEARCH_BUDGET_PER_AGENT`
- `EXTRACTION_MAX_CONCURRENCY`, `EXTRACTION_TIMEOUT_SECONDS`
- TTL values for metrics, products, and comparison caches
- Logging mode (`LOG_JSON`, `LOG_LEVEL`)

Create a `.env` file or inject vars at runtime.

## Testing & Tooling

- Async-friendly pytest configuration (`pyproject.toml`)
- Recommended extras: `pip install -e .[dev]`
- TODO: add unit tests per step, integration test for full workflow, mock Grok responses

## Next Steps

- Wire production-grade telemetry and tracing
- Implement partial-result fallback when budgets are exceeded
- Add Claude Sonnet integration toggle for Step 4 extraction quality
- Expand monitoring dashboards (cache hit rates, API cost tracking)
