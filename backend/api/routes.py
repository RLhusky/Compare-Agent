"""FastAPI routes for the product comparison service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.agent.orchestrator import ProductComparisonAgent, WorkflowBudgetExceeded
from backend.logging_config import get_logger
from backend.models.schemas import CompareRequest, ComparisonResponse
from config import get_settings

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["comparison"])


async def get_agent() -> ProductComparisonAgent:
    settings = get_settings()
    agent = ProductComparisonAgent.from_settings(settings)
    try:
        yield agent
    finally:
        await agent.close()


@router.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/compare",
    response_model=ComparisonResponse,
    status_code=status.HTTP_200_OK,
)
async def compare_products(
    payload: CompareRequest,
    agent: ProductComparisonAgent = Depends(get_agent),
) -> ComparisonResponse:
    try:
        return await agent.compare_products(payload)
    except WorkflowBudgetExceeded as exc:
        logger.warning("workflow_budget_exceeded", error=str(exc))
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning("comparison_validation_error", error=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("comparison_internal_error", error=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from exc
