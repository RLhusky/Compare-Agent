"""Implementation of the Sonar + Grok hybrid product comparison workflow."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, Sequence, TypeVar

from backend.agent import prompts
from backend.api.grok_client import GrokClient
from backend.api.sonar_client import SonarClient
from backend.cache.redis_cache import RedisCache
from backend.logging_config import get_logger
from backend.models.schemas import (
    CandidateProduct,
    ComparisonPayload,
    DisplayProduct,
    MetricComparison,
    MetricsResult,
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
class ResearchProduct:
    """Output of the Sonar product research step."""

    candidate: CandidateProduct
    extraction: ProductExtraction
    summary: str
    pros: list[str]
    cons: list[str]
    full_review: str
    price_cents: int
    title: str
    link: str
    image_source: str | None = None


def _normalize_category(category: str) -> str:
    return category.lower().strip().replace(" ", "_")


def _generate_product_id(name: str, index: int) -> str:
    base = name.lower().replace(" ", "_")
    return f"p{index + 1}_{abs(hash(base)) % 10_000_000}"


def _serialize(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


async def sonar_discovery(
    *,
    category: str,
    constraints: str | None,
    sonar_client: SonarClient,
    cache: RedisCache,
    settings: Settings,
    use_cache: bool = True,
) -> StepOutcome[MetricsResult]:
    """Run Sonar Agent A1 to validate request, derive metrics, and surface products."""

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
            metadata = {
                "products": [
                    CandidateProduct.model_validate(product) for product in cached.get("products", [])
                ],
                "searches_used": cached.get("searches_used", 0),
                "status": cached.get("status", "SUCCESS"),
                "cached": True,
            }
            return StepOutcome(data=metrics, api_calls=0, used_cache=True, metadata=metadata)
        logger.info("metrics_cache_miss", category=category)

    user_prompt = (
        f"Requested comparison category: {category}\n"
        f"User constraints or preferences: {constraints or 'None'}\n"
        "Return JSON response using the exact schema described in the system prompt."
    )

    response, search_steps = await sonar_client.call(
        system_prompt=prompts.SYSTEM_PROMPT_A1,
        user_prompt=user_prompt,
        max_searches=settings.a1_search_budget,
        timeout_seconds=settings.workflow_timeout_seconds,
        temperature=0.1,
        max_tokens=1000,
    )

    content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.exception("sonar_discovery_parse_failed", content=content)
        raise ValueError("Discovery output is not valid JSON") from exc

    status = payload.get("status", "UNKNOWN")
    if status != "SUCCESS":
        logger.warning("sonar_discovery_not_topical", status=status, category=category)
        raise ValueError("Request is not a topical consumer product comparison.")

    metrics = payload.get("metrics") or []
    if not isinstance(metrics, list) or not all(isinstance(m, str) for m in metrics):
        raise ValueError("Discovery metrics must be a list of strings.")

    product_entries = payload.get("products") or []
    products: list[CandidateProduct] = []
    for idx, item in enumerate(product_entries):
        if not isinstance(item, dict):
            continue
        name = item.get("product_name") or item.get("name")
        if not name:
            logger.warning("sonar_discovery_missing_product_name", item=item)
            continue
        product_id = item.get("product_id") or _generate_product_id(name, idx)
        products.append(
            CandidateProduct(
                product_id=product_id,
                name=name,
                discovery_method="sonar_a1",
                confidence="high",
            )
        )

    if len(products) == 0:
        raise ValueError("Sonar discovery did not return any products.")

    metrics_result = MetricsResult(category=category, metrics=list(dict.fromkeys(metrics)))
    await cache.set_json(
        cache_key,
        {
            "metrics": metrics_result.metrics,
            "cached_at": datetime.utcnow().isoformat(),
            "products": [product.model_dump(mode="json") for product in products],
            "searches_used": search_steps,
            "status": status,
        },
        ttl_seconds=settings.metrics_ttl_seconds,
    )

    metadata = {
        "products": products,
        "searches_used": search_steps,
        "status": status,
        "cached": False,
    }
    return StepOutcome(data=metrics_result, api_calls=1, metadata=metadata)


def _product_cache_key(product: CandidateProduct) -> str:
    today_key = datetime.utcnow().strftime("%Y%m%d")
    identifier = product.product_id or product.name.lower().strip().replace(" ", "_")
    return f"product:{identifier}:{today_key}"


async def _load_cached_research(
    *,
    cache: RedisCache,
    product: CandidateProduct,
) -> ResearchProduct | None:
    cached_payload = await cache.get_json(_product_cache_key(product))
    if not cached_payload:
        return None
    try:
        extraction = ProductExtraction.model_validate(cached_payload["extraction"])
        return ResearchProduct(
            candidate=product,
            extraction=extraction,
            summary=cached_payload["summary"],
            pros=list(cached_payload.get("pros", [])),
            cons=list(cached_payload.get("cons", [])),
            full_review=cached_payload["full_review"],
            price_cents=int(cached_payload.get("price_cents", 0)),
            title=cached_payload["title"],
            link=cached_payload["link"],
            image_source=cached_payload.get("image_source"),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("product_cache_deserialize_failed", product=product.name, error=str(exc))
        return None


async def _store_cached_research(
    *,
    cache: RedisCache,
    product: CandidateProduct,
    research: ResearchProduct,
    settings: Settings,
) -> None:
    payload = {
        "extraction": research.extraction.model_dump(mode="json"),
        "summary": research.summary,
        "pros": research.pros,
        "cons": research.cons,
        "full_review": research.full_review,
        "price_cents": research.price_cents,
        "title": research.title,
        "link": research.link,
        "image_source": research.image_source,
    }
    await cache.set_json(_product_cache_key(product), payload, ttl_seconds=settings.product_ttl_seconds)


async def _run_image_search(
    *,
    sonar_client: SonarClient,
    product_name: str,
    product_id: str,
    settings: Settings,
) -> tuple[str, str | None]:
    user_prompt = (
        f"Product: {product_name}\n"
        "Find a high-quality product image URL. Return JSON per the schema."
    )
    response, _ = await sonar_client.call(
        system_prompt=prompts.SYSTEM_PROMPT_IMAGE_SEARCH.format(product_name=product_name),
        user_prompt=user_prompt,
        max_searches=1,
        timeout_seconds=settings.sonar_timeout_seconds,
        temperature=0.0,
        max_tokens=200,
    )
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("image_search_parse_failed", product=product_name, content=content)
        return f"https://cdn.comparoo.com/placeholder/{product_id}.png", "placeholder"

    image_url = payload.get("image_url")
    image_source = payload.get("image_source")
    if not image_url:
        logger.warning("image_search_missing_url", product=product_name)
        return f"https://cdn.comparoo.com/placeholder/{product_id}.png", "placeholder"
    return image_url, image_source


async def _run_product_research(
    *,
    sonar_client: SonarClient,
    product: CandidateProduct,
    metrics: Sequence[str],
    settings: Settings,
) -> tuple[ResearchProduct, int]:
    metrics_list = ", ".join(metrics)
    product_id = product.product_id or _generate_product_id(product.name, 0)
    user_prompt = (
        f"Product to research: {product.name}\n"
        f"Product ID: {product_id}\n"
        f"Comparison metrics: {metrics_list}\n"
        f"You have maximum {settings.b_search_budget_per_agent} searches.\n"
        "Return JSON per the specification in the system prompt."
    )

    response, search_steps = await sonar_client.call(
        system_prompt=prompts.SYSTEM_PROMPT_B.format(product_name=product.name),
        user_prompt=user_prompt,
        max_searches=settings.b_search_budget_per_agent,
        timeout_seconds=settings.sonar_timeout_seconds,
        temperature=0.1,
        max_tokens=1400,
    )
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.warning("sonar_research_parse_failed", product=product.name, content=content)
        raise ValueError("Product research output is not valid JSON") from exc

    title = payload.get("title") or product.name
    link = payload.get("link") or payload.get("purchase_link")
    if not link:
        raise ValueError("Product research did not return a purchase link.")
    price_cents = payload.get("price")
    if isinstance(price_cents, str):
        try:
            price_cents = int(price_cents)
        except ValueError:
            price_cents = 0
    if not isinstance(price_cents, int):
        price_cents = 0

    image_url = payload.get("image_url")
    image_source = payload.get("image_source")
    if not image_url:
        image_url, image_source = await _run_image_search(
            sonar_client=sonar_client,
            product_name=product.name,
            product_id=product_id,
            settings=settings,
        )
        search_steps += 1

    description = payload.get("summary") or payload.get("description") or ""
    pros = payload.get("pros") or []
    cons = payload.get("cons") or []
    full_review = payload.get("full_review") or ""
    review_url = payload.get("review_url")
    rating = payload.get("rating")
    extraction_confidence = payload.get("extraction_confidence") or payload.get("confidence") or "medium"
    is_affiliate = bool(payload.get("is_affiliate", False))

    extraction = ProductExtraction(
        product_id=product_id,
        name=title,
        image_url=image_url,
        link=link,
        is_affiliate=is_affiliate,
        description=description,
        rating=rating,
        review_url=review_url,
        extraction_confidence=extraction_confidence,
    )

    research = ResearchProduct(
        candidate=CandidateProduct(
            product_id=product_id,
            name=title,
            discovery_method=product.discovery_method,
            confidence=product.confidence,
            source=product.source,
            source_url=product.source_url,
        ),
        extraction=extraction,
        summary=payload.get("summary") or "",
        pros=list(pros),
        cons=list(cons),
        full_review=full_review,
        price_cents=price_cents,
        title=title,
        link=link,
        image_source=image_source,
    )
    return research, search_steps


async def research_products(
    *,
    products: Sequence[CandidateProduct],
    sonar_client: SonarClient,
    cache: RedisCache,
    settings: Settings,
    metrics: Sequence[str],
    use_cache: bool = True,
) -> StepOutcome[list[ResearchProduct]]:
    """Run Sonar Agent B in parallel to gather structured product data."""

    if not products:
        return StepOutcome(data=[], api_calls=0, metadata={"searches_used": 0, "failures": 0})

    semaphore = asyncio.Semaphore(settings.extraction_max_concurrency)
    successes: list[ResearchProduct] = []
    failures: list[dict[str, Any]] = []
    cache_hits = 0
    total_searches = 0

    async def worker(candidate: CandidateProduct) -> None:
        nonlocal cache_hits, total_searches
        if use_cache:
            cached = await _load_cached_research(cache=cache, product=candidate)
            if cached:
                cache_hits += 1
                successes.append(cached)
                return
        async with semaphore:
            try:
                research, searches = await _run_product_research(
                    sonar_client=sonar_client,
                    product=candidate,
                    metrics=metrics,
                    settings=settings,
                )
                total_searches += searches
                await _store_cached_research(
                    cache=cache,
                    product=candidate,
                    research=research,
                    settings=settings,
                )
                successes.append(research)
            except Exception as exc:
                logger.error(
                    "product_research_failed",
                    product=candidate.name,
                    error=str(exc),
                )
                failures.append({"product": candidate, "error": str(exc)})

    await asyncio.gather(*(worker(product) for product in products))

    metadata = {
        "searches_used": total_searches,
        "cache_hits": cache_hits,
        "failures": [
            {"product": failure["product"].name, "error": failure["error"]} for failure in failures
        ],
    }
    api_calls = total_searches + len(failures)
    return StepOutcome(data=successes, api_calls=api_calls, used_cache=cache_hits > 0, metadata=metadata)


def _match_research_product(
    rankings_entry: dict[str, Any],
    research_products: Sequence[ResearchProduct],
) -> ResearchProduct | None:
    product_id = rankings_entry.get("product_id")
    if product_id:
        for product in research_products:
            if product.candidate.product_id == product_id or product.extraction.product_id == product_id:
                return product
    title = rankings_entry.get("product_title")
    if title:
        normalized_title = title.lower().strip()
        for product in research_products:
            if product.title.lower().strip() == normalized_title:
                return product
    return None


def _build_metric_comparison_table(payload: dict[str, Any]) -> MetricComparison:
    table = payload.get("comparison_table") or {}
    headers = table.get("headers") or []
    rows = table.get("rows") or []
    return MetricComparison(headers=list(headers), rows=[list(row) for row in rows])


async def generate_comparison_payload(
    *,
    research_products: Sequence[ResearchProduct],
    metrics: Sequence[str],
    grok_client: GrokClient,
) -> StepOutcome[ComparisonPayload]:
    """Use Grok Agent C to rank products, assign star ratings, and build comparison table."""

    if not research_products:
        raise ValueError("No product research data available for comparison.")

    reviews_text = ""
    for product in research_products:
        reviews_text += (
            f"Product ID: {product.extraction.product_id}\n"
            f"Product Title: {product.title}\n"
            f"Price (USD cents): {product.price_cents}\n"
            f"Summary: {product.summary}\n"
            f"Pros: {', '.join(product.pros)}\n"
            f"Cons: {', '.join(product.cons)}\n"
            f"Full Review: {product.full_review}\n"
            "---\n"
        )

    user_prompt = (
        f"Products to compare:\n{reviews_text}\n\n"
        f"Comparison metrics: {', '.join(metrics)}\n"
        f"Return JSON per the required structure."
    )

    response = await grok_client.reasoning_call(
        system_prompt=prompts.SYSTEM_PROMPT_C,
        user_prompt=user_prompt,
        enable_search=False,
        temperature=0.4,
        max_tokens=1400,
    )
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.exception("grok_comparison_parse_failed", content=content)
        raise ValueError("Comparison synthesis output is not valid JSON") from exc

    table = _build_metric_comparison_table(payload)
    rankings = payload.get("rankings") or []
    summary_text = payload.get("summary") or ""

    ordered_products: list[DisplayProduct] = []
    narratives: list[str] = []
    for entry in rankings:
        product = _match_research_product(entry, research_products)
        if not product:
            logger.warning(
                "ranking_product_unmatched",
                product_title=entry.get("product_title"),
                product_id=entry.get("product_id"),
            )
            continue

        rating = entry.get("rating")
        rating_str = f"{float(rating):.1f}/5.0" if isinstance(rating, (int, float)) else product.extraction.rating
        rationale = entry.get("rationale") or ""
        best_for = entry.get("best_for")
        if rationale:
            narratives.append(f"Rank {entry.get('rank')}: {product.title} - {rationale}")
        if best_for:
            narratives.append(f"Best for {best_for}: {product.title}")

        ordered_products.append(
            DisplayProduct(
                product_id=product.extraction.product_id,
                name=product.title,
                image_url=product.extraction.image_url,
                link=product.link,
                is_affiliate=product.extraction.is_affiliate,
                description=product.extraction.description or product.summary,
                rating=rating_str,
                review_url=product.extraction.review_url,
                extraction_confidence=product.extraction.extraction_confidence,
                strengths=product.pros,
                weaknesses=product.cons,
            )
        )

    if not ordered_products:
        raise ValueError("Comparison synthesis did not return any ranked products.")

    comparison_payload = ComparisonPayload(
        comparison_summary=summary_text or "Top picks ranked by Comparoo.",
        full_comparison="\n\n".join(narratives) if narratives else summary_text,
        products=ordered_products,
        metrics_table=table,
    )

    metadata = {"rankings": rankings}
    return StepOutcome(data=comparison_payload, api_calls=1, metadata=metadata)


__all__ = [
    "ResearchProduct",
    "StepOutcome",
    "generate_comparison_payload",
    "research_products",
    "sonar_discovery",
]

