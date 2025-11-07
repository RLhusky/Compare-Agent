# Product Comparison Agent

Agentic backend for a scalable product comparison website powered by Grok 4 Fast.  
The service orchestrates a six-step workflow that discovers comparison metrics, lifts
products from authoritative review sites, extracts mandatory product data in parallel,
generates comparisons, and formats the results for frontend consumption — all while
respecting strict compute and API budgets.

## Key Capabilities
- Grok 4 Fast reasoning/non-reasoning modes with native search integration
- Hard-coded fallback discovery strategies for resilient product sourcing
- Parallel Step 4 extraction with concurrency/budget controls
- Aggressive Redis caching across metrics, product data, and comparisons
- Structured FastAPI endpoint returning ready-to-render payloads
- Centralized logging, error handling, and budget enforcement

## Project Layout
```
backend/
  agent/
    orchestrator.py   # Workflow coordinator
    prompts.py        # Prompt templates for each step
    steps.py          # Step implementations
  api/
    grok_client.py    # HTTP client wrapper with retries & timeouts
    routes.py         # FastAPI routes (compare + health)
  cache/
    redis_cache.py    # Redis-backed cache helper
  logging_config.py   # structlog configuration utilities
  models/
    schemas.py        # Pydantic models for requests/responses
config.py             # Environment-driven settings
main.py               # FastAPI application entry point
pyproject.toml        # Dependencies and tooling
```

## Six-Step Workflow
1. **Metric Discovery** (`grok-4-fast-reasoning`)  
   Cached per category for 90 days to minimize reasoning calls.
2. **Ranking Site Harvesting** (`grok-4-fast-reasoning` + search)  
   Targets Wirecutter, RTINGS, Consumer Reports, etc.
3. **Fallback Discovery** (`grok-4-fast-reasoning` + search)  
   Deterministic strategies (bestsellers, Amazon, Reddit, forums).
4. **Product Extraction** (`grok-4-fast-non-reasoning`, parallel ≤5)  
   Mandatory fields enforced; cache refreshed every 12 hours.
5. **Comparison Generation** (`grok-4-fast-reasoning`)  
   Produces markdown analysis covering metrics, strengths, recommendations.
6. **Display Formatting** (`grok-4-fast-non-reasoning`)  
   Returns structured JSON for UI cards and metric tables.

Compute budgets are enforced end-to-end (`MAX_API_CALLS=8`, `workflow_timeout≤32s`).

## Configuration
All settings are defined in `config.py` (Pydantic BaseSettings).  
Environment variables (with defaults) include:

- `GROK_API_KEY` / `GROK_BASE_URL`
- `REDIS_URL`
- `MAX_API_CALLS_PER_COMPARISON`
- `WORKFLOW_TIMEOUT_SECONDS`, `STEP_TIMEOUT_SECONDS`
- `EXTRACTION_MAX_CONCURRENCY`, `EXTRACTION_TIMEOUT_SECONDS`
- TTL values for metrics, products, and comparison caches
- Logging mode (`LOG_JSON`, `LOG_LEVEL`)

Create a `.env` file or inject vars at runtime.

## Running Locally
```bash
pip install -e .
uvicorn main:app --reload
```

The API exposes:
- `GET /api/health` – readiness probe
- `POST /api/compare` – body `{"category": "...", "constraints": "...optional..."}`  
  Returns `ComparisonResponse` containing metrics, formatted comparison payload, and workflow stats.

## Testing & Tooling
- Async-friendly pytest configuration (`pyproject.toml`)
- Recommended extras: `pip install -e .[dev]`
- TODO: add unit tests per step, integration test for full workflow, mock Grok responses

## Next Steps
- Wire production-grade telemetry and tracing
- Implement partial-result fallback when budgets are exceeded
- Add Claude Sonnet integration toggle for Step 4 extraction quality
- Expand monitoring dashboards (cache hit rates, API cost tracking)
