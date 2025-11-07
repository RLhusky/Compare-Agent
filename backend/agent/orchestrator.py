"""Agent orchestrator that coordinates the end-to-end comparison workflow."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from time import perf_counter
from typing import Sequence

from backend.agent import steps
from backend.api.grok_client import GrokClient
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

    client: GrokClient
    cache: RedisCache
    settings: Settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ProductComparisonAgent":
        settings = settings or get_settings()
        client = GrokClient(settings=settings)
        cache = RedisCache(url=settings.redis_url, enabled=settings.cache_enabled)
        return cls(client=client, cache=cache, settings=settings)

    async def close(self) -> None:
        await self.client.close()
        await self.cache.close()

    async def compare_products(self, request: CompareRequest) -> ComparisonResponse:
        """Run the agent workflow end-to-end."""

        start_time = perf_counter()
        api_calls = 0
        used_fallback = False
        category = request.category
        constraints = request.constraints
        cache_hash = _hash_query(category.lower().strip(), constraints)
        comparison_cache_key = f"comparison:{cache_hash}"

        if request.use_cache:
            cached_response = await self.cache.get_json(comparison_cache_key)
            if cached_response:
                logger.info("comparison_cache_hit", category=category, constraints=constraints)
                cached_response["cached_result"] = True
                response = ComparisonResponse.model_validate(cached_response)
                return response

        async with asyncio.timeout(self.settings.workflow_timeout_seconds):
            metrics_outcome = await steps.discover_metrics(
                category=category,
                client=self.client,
                cache=self.cache,
                settings=self.settings,
                use_cache=request.use_cache,
            )
            metrics_result = metrics_outcome.data
            api_calls += metrics_outcome.api_calls

            self._ensure_budget(api_calls)

            ranking_outcome = await steps.find_products_from_ranking_sites(
                category=category,
                constraints=constraints,
                client=self.client,
            )
            api_calls += ranking_outcome.api_calls
            self._ensure_budget(api_calls)

            candidates = ranking_outcome.data
            confidence = ranking_outcome.metadata.get("confidence", "low")
            if len(candidates) < 3 or confidence == "low":
                used_fallback = True
                fallback_outcome = await steps.fallback_discovery(
                    category=category,
                    constraints=constraints,
                    client=self.client,
                )
                api_calls += fallback_outcome.api_calls
                self._ensure_budget(api_calls)
                candidates = self._merge_candidates(candidates, fallback_outcome.data)

            if not candidates:
                raise ValueError("No products discovered for comparison.")

            extraction_outcome = await steps.extract_product_data(
                products=candidates,
                client=self.client,
                settings=self.settings,
                cache=self.cache,
                use_cache=request.use_cache,
            )
            api_calls += extraction_outcome.api_calls
            self._ensure_budget(api_calls)

            extracted_products = extraction_outcome.data
            if len(extracted_products) < 2:
                raise ValueError("Insufficient product data extracted.")

            comparison_outcome = await steps.generate_comparison_analysis(
                products=extracted_products,
                metrics=metrics_result.metrics,
                client=self.client,
            )
            api_calls += comparison_outcome.api_calls
            self._ensure_budget(api_calls)

            comparison_text = comparison_outcome.data

            formatting_outcome = await steps.format_for_display(
                comparison_text=comparison_text,
                products=extracted_products,
                metrics=metrics_result.metrics,
                client=self.client,
            )
            api_calls += formatting_outcome.api_calls
            self._ensure_budget(api_calls)

            comparison_payload = formatting_outcome.data
            display_products = comparison_payload.products

            stats = WorkflowStats(
                api_calls=api_calls,
                duration_seconds=perf_counter() - start_time,
                used_fallback=used_fallback,
                source_summary=self._summarize_sources(candidates),
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
    def _merge_candidates(primary: Sequence[CandidateProduct], fallback: Sequence[CandidateProduct]) -> list[CandidateProduct]:
        combined: dict[str, CandidateProduct] = {candidate.name: candidate for candidate in primary}
        for candidate in fallback:
            combined.setdefault(candidate.name, candidate)
        return list(combined.values())

    @staticmethod
    def _summarize_sources(candidates: Sequence[CandidateProduct]) -> dict[str, int]:
        summary: dict[str, int] = {}
        for candidate in candidates:
            key = candidate.discovery_method or "unknown"
            summary[key] = summary.get(key, 0) + 1
        return summary
