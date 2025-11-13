"""Agent orchestrator that coordinates the end-to-end comparison workflow."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Sequence

from backend.api.glm_client import GlmClient
from backend.agent.steps import (
    ProductResearch,
    glm_discovery,
    research_products,
    generate_comparison_payload,
)
from backend.cache.redis_cache import RedisCache
from backend.logging_config import get_logger
from backend.models.schemas import CandidateProduct, CompareRequest, ComparisonResponse, WorkflowStats
from config import Settings, get_settings

logger = get_logger(__name__)


class WorkflowBudgetExceeded(RuntimeError):
    """Raised when API call or time budgets are exceeded."""


def _hash_query(category: str, constraints: str | None) -> str:
    payload = f"{category}|{constraints or ''}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(slots=True)
class ProductComparisonAgent:
    """Coordinates the multi-step agent workflow."""

    glm_client: GlmClient
    cache: RedisCache
    settings: Settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ProductComparisonAgent":
        settings = settings or get_settings()
        glm_client = GlmClient(settings=settings)
        cache = RedisCache(url=settings.redis_url, enabled=settings.cache_enabled)
        return cls(glm_client=glm_client, cache=cache, settings=settings)

    async def close(self) -> None:
        await self.glm_client.close()
        await self.cache.close()

    async def compare_products(
        self, request: CompareRequest, progress_callback: Callable[[dict[str, Any]], None] | None = None
    ) -> ComparisonResponse:
        """Run the agent workflow end-to-end."""

        start_time = perf_counter()
        api_calls = 0
        used_fallback = False
        category = request.category
        constraints = request.constraints
        cache_hash = _hash_query(category.lower().strip(), constraints)
        comparison_cache_key = f"comparison:{cache_hash}"
        step_timings: dict[str, float] = {}

        if request.use_cache:
            cached_response = await self.cache.get_json(comparison_cache_key)
            if cached_response:
                logger.info("comparison_cache_hit", category=category, constraints=constraints)
                cached_response["cached_result"] = True
                response = ComparisonResponse.model_validate(cached_response)
                if progress_callback:
                    progress_callback({"step": "discovery", "status": "complete", "progress": 33})
                    progress_callback({"step": "research", "status": "complete", "progress": 66})
                    progress_callback({"step": "comparison", "status": "complete", "progress": 100})
                return response

        async with asyncio.timeout(self.settings.workflow_timeout_seconds):
            discovery_start = perf_counter()
            discovery_outcome = await glm_discovery(
                settings=self.settings,
                category=category,
                constraints=constraints,
                glm_client=self.glm_client,
                cache=self.cache,
                use_cache=request.use_cache,
            )
            discovery_duration = perf_counter() - discovery_start
            step_timings["discovery"] = discovery_duration
            metrics_result = discovery_outcome.data
            api_calls += discovery_outcome.api_calls
            self._ensure_budget(api_calls)

            # Notify progress: Discovery complete
            if progress_callback:
                progress_callback({"step": "discovery", "status": "complete", "progress": 33})

            candidates = discovery_outcome.metadata.get("products", [])
            if not candidates:
                raise ValueError("Discovery did not return any products.")

            logger.info(
                "workflow_step_completed",
                step="discovery",
                duration_seconds=discovery_duration,
                candidate_count=len(candidates),
                searches_used=discovery_outcome.metadata.get("searches_used"),
            )

            research_start = perf_counter()
            research_outcome = await research_products(
                settings=self.settings,
                products=candidates,
                glm_client=self.glm_client,
                cache=self.cache,
                use_cache=request.use_cache,
            )
            research_duration = perf_counter() - research_start
            step_timings["research"] = research_duration
            api_calls += research_outcome.api_calls
            self._ensure_budget(api_calls)

            # Notify progress: Research complete
            if progress_callback:
                progress_callback({"step": "research", "status": "complete", "progress": 66})

            research_products = research_outcome.data
            if len(research_products) < 2:
                raise ValueError("Insufficient product data extracted.")

            logger.info(
                "product_research_summary",
                product_count=len(research_products),
                **research_outcome.metadata,
            )

            logger.info(
                "workflow_step_completed",
                step="research",
                duration_seconds=research_duration,
                product_count=len(research_products),
                cache_hits=research_outcome.metadata.get("cache_hits"),
                failures=len(research_outcome.metadata.get("failures", [])),
            )

            comparison_start = perf_counter()
            comparison_outcome = await generate_comparison_payload(
                settings=self.settings,
                theme=discovery_outcome.theme,
                research=research_outcome.research,
                telemetry=telemetry,
                glm_client=self.glm_client,
            )
            comparison_duration = perf_counter() - comparison_start
            step_timings["comparison"] = comparison_duration
            api_calls += comparison_outcome.api_calls
            self._ensure_budget(api_calls)

            # Notify progress: Comparison complete
            if progress_callback:
                progress_callback({"step": "comparison", "status": "complete", "progress": 100})

            comparison_payload = comparison_outcome.data
            display_products = comparison_payload.products

            logger.info(
                "workflow_step_completed",
                step="comparison",
                duration_seconds=comparison_duration,
                ranked_count=len(display_products),
            )

            stats = WorkflowStats(
                api_calls=api_calls,
                duration_seconds=perf_counter() - start_time,
                used_fallback=used_fallback,
                source_summary=self._summarize_sources(candidates),
                extraction_metrics={
                    "research": research_outcome.metadata,
                    "comparison": comparison_outcome.metadata,
                    "discovery": {
                        "searches_used": discovery_outcome.metadata.get("searches_used", 0),
                        "status": discovery_outcome.metadata.get("status"),
                    },
                },
                step_durations_seconds=step_timings,
            )

            response = ComparisonResponse(
                request=request,
                metrics=metrics_result,
                products=display_products,
                comparison=comparison_payload,
                stats=stats,
                cached_result=False,
            )

            if request.use_cache and self.cache.enabled:
                await self.cache.set_json(
                    comparison_cache_key,
                    response.model_dump(mode="json"),
                    ttl_seconds=self.settings.comparison_ttl_seconds,
                )

            return response

    def _ensure_budget(self, api_calls: int) -> None:
        if api_calls > self.settings.max_api_calls_per_comparison:
            raise WorkflowBudgetExceeded("API call budget exceeded for comparison request.")

    @staticmethod
    def _summarize_sources(candidates: Sequence[CandidateProduct]) -> dict[str, int]:
        summary: dict[str, int] = {}
        for candidate in candidates:
            key = candidate.discovery_method or "unknown"
            summary[key] = summary.get(key, 0) + 1
        return summary
