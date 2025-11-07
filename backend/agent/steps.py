"""Implementation of the six-step product comparison workflow."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, Sequence, TypeVar

from backend.agent import prompts
from backend.api.grok_client import GrokClient
from backend.cache.redis_cache import RedisCache
from backend.logging_config import get_logger
from backend.models.schemas import (
    CandidateProduct,
    ComparisonPayload,
    DisplayProduct,
    MetricsResult,
    MetricComparison,
    ProductExtraction,
)
from config import Settings

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass(slots=True)
class StepOutcome(Generic[T]):
    """Container that tracks API calls and metadata for each workflow step."""

    data: T
    api_calls: int = 0
    used_cache: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExtractionResult:
    """Represents the outcome of a single product extraction attempt."""

    data: ProductExtraction | None
    used_api: bool
    from_cache: bool
    error: str | None = None


def _normalize_category(category: str) -> str:
    return category.lower().strip().replace(" ", "_")


def _serialize(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


async def discover_metrics(
    *,
    category: str,
    client: GrokClient,
    cache: RedisCache,
    settings: Settings,
    use_cache: bool = True,
) -> StepOutcome[MetricsResult]:
    """Step 1: Identify comparison metrics with caching."""

    cache_key = f"metrics:{_normalize_category(category)}"
    if use_cache:
        cached = await cache.get_json(cache_key)
        if cached and isinstance(cached, dict) and "metrics" in cached:
            logger.info("metrics_cache_hit", category=category)
            metrics = MetricsResult(
                category=category,
                metrics=cached["metrics"],
                cached=True,
                cached_at=datetime.fromisoformat(cached["cached_at"])
                if cached.get("cached_at")
                else None,
            )
            return StepOutcome(data=metrics, api_calls=0, used_cache=True)
        logger.info("metrics_cache_miss", category=category)

    prompt_text = prompts.METRIC_DISCOVERY_PROMPT.format(category=category)
    response = await client.reasoning_call(
        system_prompt="You are a structured data assistant.",
        user_prompt=prompt_text,
        enable_search=False,
        temperature=0.4,
        max_tokens=400,
    )
    message = response.get("choices", [{}])[0].get("message", {})
    content = message.get("content", "[]")
    try:
        metrics_list = json.loads(content)
    except json.JSONDecodeError as exc:  # pragma: no cover - LLM parsing
        logger.exception("metrics_parse_failed", content=content)
        raise ValueError("Unable to parse metrics JSON") from exc

    if not isinstance(metrics_list, list) or not all(isinstance(m, str) for m in metrics_list):
        raise ValueError("Metrics output must be a list of strings")

    metrics_result = MetricsResult(category=category, metrics=list(dict.fromkeys(metrics_list)))
    await cache.set_json(
        cache_key,
        {"metrics": metrics_result.metrics, "cached_at": datetime.utcnow().isoformat()},
        ttl_seconds=settings.metrics_ttl_seconds,
    )
    return StepOutcome(data=metrics_result, api_calls=1)


async def find_products_from_ranking_sites(
    *,
    category: str,
    constraints: str | None,
    client: GrokClient,
) -> StepOutcome[list[CandidateProduct]]:
    """Step 2: Query authoritative review sites."""

    user_prompt = prompts.RANKING_SITE_PROMPT.format(category=category, constraints=constraints or "None")
    response = await client.reasoning_call(
        system_prompt="You specialize in surfacing authoritative review site recommendations.",
        user_prompt=user_prompt,
        enable_search=True,
        temperature=0.5,
        max_tokens=700,
    )

    content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.exception("ranking_sites_parse_failed", content=content)
        raise ValueError("Ranking site output is not valid JSON") from exc

    products_payload = payload.get("products", []) if isinstance(payload, dict) else []
    confidence = payload.get("confidence", "low") if isinstance(payload, dict) else "low"
    products: list[CandidateProduct] = []

    for item in products_payload:
        if not isinstance(item, dict):
            continue
        try:
            products.append(
                CandidateProduct(
                    name=item["name"],
                    source=item.get("source"),
                    source_url=item.get("source_url"),
                    discovery_method="ranking_site",
                    confidence=confidence,
                )
            )
        except KeyError:
            logger.warning("ranking_product_missing_name", item=item)
            continue

    metadata = {"confidence": confidence}
    return StepOutcome(data=products, api_calls=1, metadata=metadata)


async def fallback_discovery(
    *,
    category: str,
    constraints: str | None,
    client: GrokClient,
) -> StepOutcome[list[CandidateProduct]]:
    """Step 3: Fallback search strategies when ranking sites are insufficient."""

    user_prompt = prompts.FALLBACK_DISCOVERY_PROMPT.format(category=category, constraints=constraints or "None")
    response = await client.reasoning_call(
        system_prompt="You retrieve product suggestions from popular sources without inventing data.",
        user_prompt=user_prompt,
        enable_search=True,
        temperature=0.5,
        max_tokens=700,
    )
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.exception("fallback_parse_failed", content=content)
        raise ValueError("Fallback discovery output is not valid JSON") from exc

    products_payload = payload.get("products", []) if isinstance(payload, dict) else []
    products: list[CandidateProduct] = []
    for item in products_payload:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name:
            logger.warning("fallback_product_missing_name", item=item)
            continue
        discovery_method = item.get("discovery_method") or "best_sellers"
        products.append(
            CandidateProduct(
                name=name,
                discovery_method=discovery_method,
                source_url=item.get("source_url"),
                source=item.get("source"),
                confidence="medium",
            )
        )

    return StepOutcome(data=products, api_calls=1)


async def _extract_single_product(
    *,
    client: GrokClient,
    product: CandidateProduct,
    settings: Settings,
    cache: RedisCache,
    use_cache: bool,
) -> ExtractionResult:
    """Run Step 4 extraction for a single product with caching."""

    normalized = product.name.lower().strip().replace(" ", "_")
    today_key = datetime.utcnow().strftime("%Y%m%d")
    cache_key = f"product:{normalized}:{today_key}"

    if use_cache:
        cached_payload = await cache.get_json(cache_key)
        if cached_payload:
            try:
                extraction = ProductExtraction.model_validate(cached_payload)
                return ExtractionResult(data=extraction, used_api=False, from_cache=True)
            except Exception:
                logger.warning("product_cache_deserialize_failed", product=product.name)

    prompt_text = prompts.EXTRACTION_PROMPT.format(
        product_name=product.name,
        source_url=product.source_url or "None",
    )

    try:
        response = await asyncio.wait_for(
            client.non_reasoning_call(
                system_prompt="You extract structured product data without fabricating values.",
                user_prompt=prompt_text,
                temperature=0.2,
                max_tokens=600,
            ),
            timeout=settings.extraction_timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning("product_extraction_timeout", product=product.name)
        return ExtractionResult(data=None, used_api=True, from_cache=False, error="timeout")

    content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("product_extraction_parse_failed", product=product.name)
        return ExtractionResult(data=None, used_api=True, from_cache=False, error="parse_error")

    mandatory_fields = ("image_url", "link", "description")
    if not all(payload.get(field) for field in mandatory_fields):
        logger.warning("product_missing_mandatory_fields", product=product.name, payload=payload)
        return ExtractionResult(data=None, used_api=True, from_cache=False, error="missing_fields")

    try:
        extraction = ProductExtraction.model_validate({"name": product.name, **payload})
    except Exception as exc:
        logger.warning("product_extraction_validation_failed", product=product.name, error=str(exc))
        return ExtractionResult(data=None, used_api=True, from_cache=False, error="validation_failed")

    await cache.set_json(cache_key, extraction.model_dump(mode="json"), ttl_seconds=settings.product_ttl_seconds)
    return ExtractionResult(data=extraction, used_api=True, from_cache=False)


async def extract_product_data(
    *,
    products: Sequence[CandidateProduct],
    client: GrokClient,
    settings: Settings,
    cache: RedisCache,
    use_cache: bool = True,
) -> StepOutcome[list[ProductExtraction]]:
    """Step 4: Parallel extraction of product metadata."""

    if not products:
        return StepOutcome(
            data=[],
            api_calls=0,
            metadata={"attempts": 0, "cache_hits": 0, "failures": 0, "timed_out": False},
        )

    semaphore = asyncio.Semaphore(settings.extraction_max_concurrency)

    async def worker(candidate: CandidateProduct) -> ExtractionResult:
        async with semaphore:
            return await _extract_single_product(
                client=client,
                product=candidate,
                settings=settings,
                cache=cache,
                use_cache=use_cache,
            )

    tasks = [asyncio.create_task(worker(product)) for product in products]
    done: set[asyncio.Task[ExtractionResult]] = set()
    pending: set[asyncio.Task[ExtractionResult]] = set()

    try:
        done, pending = await asyncio.wait(tasks, timeout=settings.step_timeout_seconds)
    except Exception as exc:  # pragma: no cover - unexpected scheduling error
        logger.exception("product_extraction_wait_failed", error=str(exc))
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        return StepOutcome(
            data=[],
            api_calls=0,
            metadata={"attempts": 0, "cache_hits": 0, "failures": 0, "timed_out": True},
        )

    if pending:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        logger.warning(
            "product_extraction_step_timeout",
            pending=len(pending),
            total=len(tasks),
            timeout=settings.step_timeout_seconds,
        )

    results: list[ExtractionResult] = []
    task_exceptions = 0
    for task in done:
        try:
            results.append(task.result())
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("product_extraction_task_exception", error=str(exc))
            task_exceptions += 1

    cache_hits = sum(1 for result in results if result.from_cache)
    extracted: list[ProductExtraction] = [result.data for result in results if result.data]
    extracted.sort(key=lambda p: p.name)

    api_attempts = sum(1 for result in results if result.used_api)
    failures = sum(1 for result in results if result.used_api and result.data is None)

    if task_exceptions:
        api_attempts += task_exceptions
        failures += task_exceptions

    if pending:
        api_attempts += len(pending)
        failures += len(pending)

    metadata = {
        "total_candidates": len(products),
        "attempts": api_attempts,
        "cache_hits": cache_hits,
        "failures": failures,
        "timed_out": bool(pending),
    }

    return StepOutcome(
        data=extracted,
        api_calls=api_attempts,
        used_cache=cache_hits > 0,
        metadata=metadata,
    )


async def generate_comparison_analysis(
    *,
    products: Sequence[ProductExtraction],
    metrics: Sequence[str],
    client: GrokClient,
) -> StepOutcome[str]:
    """Step 5: Generate reasoning-driven comparison."""

    if not products or not metrics:
        raise ValueError("Products and metrics are required for comparison generation")

    user_prompt = prompts.COMPARISON_PROMPT.format(
        products_json=_serialize([p.model_dump(mode="json") for p in products]),
        metrics_array=_serialize(list(metrics)),
    )
    response = await client.reasoning_call(
        system_prompt="Provide balanced, evidence-based product comparisons.",
        user_prompt=user_prompt,
        enable_search=False,
        temperature=0.5,
        max_tokens=1000,
    )
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    return StepOutcome(data=content, api_calls=1)


async def format_for_display(
    *,
    comparison_text: str,
    products: Sequence[ProductExtraction],
    metrics: Sequence[str],
    client: GrokClient,
) -> StepOutcome[ComparisonPayload]:
    """Step 6: Transform comparison text and products into frontend payload."""

    user_prompt = prompts.FORMAT_PROMPT.format(
        comparison_text=comparison_text,
        products_with_data=_serialize([p.model_dump(mode="json") for p in products]),
        metrics=_serialize(list(metrics)),
    )

    response = await client.non_reasoning_call(
        system_prompt="Format data into JSON suitable for frontend rendering.",
        user_prompt=user_prompt,
        temperature=0.1,
        max_tokens=900,
    )
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.exception("formatting_parse_failed", content=content)
        raise ValueError("Formatting output is not valid JSON") from exc

    products_payload = payload.get("products", []) if isinstance(payload, dict) else []
    formatted_products: list[DisplayProduct] = []
    for item in products_payload:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name:
            continue
        source_extraction = next((p for p in products if p.name == name), None)
        if not source_extraction:
            continue
        merged = {**source_extraction.model_dump(mode="json"), **item}
        try:
            formatted_products.append(DisplayProduct.model_validate(merged))
        except Exception as exc:
            logger.warning("display_product_validation_failed", product=name, error=str(exc))
            continue

    headers = []
    rows = []
    metrics_table = payload.get("metrics_table")
    if isinstance(metrics_table, dict):
        headers = metrics_table.get("headers") or []
        rows = metrics_table.get("rows") or []

    comparison_payload = ComparisonPayload(
        comparison_summary=payload.get("comparison_summary", ""),
        full_comparison=payload.get("full_comparison", comparison_text),
        products=formatted_products,
        metrics_table=MetricComparison(headers=headers, rows=rows),
    )
    return StepOutcome(data=comparison_payload, api_calls=1)
