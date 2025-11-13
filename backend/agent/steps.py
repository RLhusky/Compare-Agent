"""Implementation of the GLM-based product comparison workflow using OpenRouter."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from urllib.parse import quote, urlparse
from typing import Any, Generic, Sequence, TypeVar

import httpx

from backend.agent import prompts
from backend.api.glm_client import GlmClient
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
    """Output of the GLM product research step."""

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


def _strip_json_fences(content: str) -> str:
    """Remove markdown code fences from LLM responses."""

    text = content.strip()
    if text.startswith("```"):
        # Remove opening fence and optional language hint
        text = text[3:]
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.lstrip()
        if "```" in text:
            text = text.rsplit("```", 1)[0]
    return text.strip()


def _format_price_cents(value: int | None) -> str | None:
    if value is None or value <= 0:
        return None
    dollars = value / 100
    return f"${dollars:,.2f}"


def _proxy_image_url(url: str) -> str:
    """Route external image URLs through a proxy to improve load success."""

    if not url:
        return url

    parsed = urlparse(url)
    if not parsed.netloc:
        return url

    # Keep internal placeholders unmodified
    if parsed.netloc.endswith("comparoo.com"):
        return url

    proxy_target = parsed.netloc + parsed.path
    if parsed.query:
        proxy_target += f"?{parsed.query}"

    safe_target = quote(proxy_target, safe="/?=&:%+-_.")
    if parsed.scheme == "https":
        return f"https://images.weserv.nl/?url=ssl:{safe_target}"
    return f"https://images.weserv.nl/?url={safe_target}"


async def _fetch_open_graph_image(link: str) -> str | None:
    """Try to extract the Open Graph image from the target product page."""

    if not link or not (link.startswith("http://") or link.startswith("https://")):
        return None

    try:
        timeout = httpx.Timeout(2.5, connect=1.0)
        headers = {
            "User-Agent": "ComparooBot/1.0 (+https://comparoo.com)",
            "Accept": "text/html,application/xhtml+xml",
        }
        async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
            response = await client.get(link)
        if response.status_code >= 400 or not response.text:
            return None

        html = response.text
        match = re.search(
            r"<meta[^>]+(?:property|name)=[\"']og:image(?::secure_url)?[\"'][^>]+content=[\"']([^\"']+)[\"']",
            html,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        candidate = match.group(1).strip()
        if candidate.startswith("//"):
            candidate = "https:" + candidate
        if candidate.startswith("http://") or candidate.startswith("https://"):
            return candidate
    except Exception as exc:  # pragma: no cover - network I/O
        logger.debug("open_graph_image_fetch_failed", link=link, error=str(exc))
    return None


_PRICE_STRING_KEYS = [
    "price_display",
    "price_formatted",
    "price_text",
    "price_string",
    "price_str",
]


def _parse_price_string(raw: str | None) -> int | None:
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None

    cleaned = re.sub(r"(usd|dollars|us\$)", "", cleaned, flags=re.IGNORECASE)
    match = re.search(r"(-?\d[\d,\.]*)", cleaned)
    if not match:
        return None

    numeric = match.group(1).replace(",", "")
    try:
        dollars = float(numeric)
    except ValueError:
        return None

    if dollars <= 0:
        return None
    return int(round(dollars * 100))


def _normalize_numeric_price(value: int | float) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if value <= 0:
            return None
        if value < 100000:
            return int(round(value * 100))
        return int(round(value))

    if isinstance(value, int):
        if value <= 0:
            return None
        digits = len(str(abs(value)))
        if value >= 1_000_000:
            return value  # already cents
        if digits >= 5:
            return value  # treat as cents (e.g., 19900 -> $199.00)
        # digits <=4 – likely dollars
        return value * 100
    return None


def _extract_price_cents(payload: dict[str, Any], product_name: str) -> tuple[int, str]:
    sources: list[tuple[str, Any]] = []
    if "price" in payload:
        sources.append(("price", payload.get("price")))
    for key in _PRICE_STRING_KEYS:
        if key in payload and payload[key]:
            sources.append((key, payload[key]))

    for key, value in sources:
        cents = _parse_price_string(value) if isinstance(value, str) else None
        if cents:
            return cents, key

    for key, value in sources:
        cents = _normalize_numeric_price(value) if isinstance(value, (int, float)) else None
        if cents:
            return cents, key

    logger.warning("price_unparsed", product=product_name, price_sources={k: v for k, v in sources})
    return 0, "unparsed"


async def glm_discovery(
    *,
    settings: Settings,
    category: str,
    constraints: str | None,
    glm_client: GlmClient,
    cache: RedisCache,
    use_cache: bool = True,
) -> StepOutcome[MetricsResult]:
    """Run GLM Agent A1 to validate request, derive metrics, and surface products."""

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

    response, search_steps = await glm_client.call(
        system_prompt=prompts.SYSTEM_PROMPT_A1,
        user_prompt=user_prompt,
        max_searches=settings.a1_search_budget,
        timeout_seconds=settings.glm_timeout_seconds or 8.0,
        temperature=0.1,
        max_tokens=2000,
    )

    # Safely extract content with error handling
    choices = response.get("choices", [])
    if not choices or len(choices) == 0:
        logger.error("glm_discovery_no_choices", category=category, response_keys=list(response.keys()))
        raise ValueError("Discovery returned no choices in response")
    
    message = choices[0].get("message", {})
    if not message:
        logger.error("glm_discovery_no_message", category=category, choice=choices[0] if choices else None)
        raise ValueError("Discovery returned no message in choice")
    
    content = message.get("content", "{}")
    if not content or content == "{}" or not content.strip():
        logger.error("glm_discovery_empty_response", category=category, finish_reason=choices[0].get("finish_reason"))
        raise ValueError("Discovery returned empty response")
    
    content = _strip_json_fences(content)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.exception("glm_discovery_parse_failed", content=content[:500])
        raise ValueError("Discovery output is not valid JSON") from exc

    status = payload.get("status", "UNKNOWN")
    if status != "SUCCESS":
        logger.warning("glm_discovery_not_topical", status=status, category=category)
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
            logger.warning("glm_discovery_missing_product_name", item=item)
            continue
        product_id = item.get("product_id") or _generate_product_id(name, idx)
        products.append(
            CandidateProduct(
                product_id=product_id,
                name=name,
                discovery_method="glm_a1",
                confidence="high",
            )
        )

    if len(products) == 0:
        raise ValueError("Discovery did not return any products.")

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
    glm_client: GlmClient,
    product_name: str,
    product_id: str,
    settings: Settings,
) -> tuple[str, str | None]:
    user_prompt = (
        f"Product: {product_name}\n"
        "Find a high-quality product image URL. Return JSON per the schema."
    )
    system_prompt_image = prompts.SYSTEM_PROMPT_IMAGE_SEARCH.replace("{product_name}", product_name)
    response, _ = await glm_client.call(
        system_prompt=system_prompt_image,
        user_prompt=user_prompt,
        max_searches=1,
        timeout_seconds=settings.glm_timeout_seconds or 8.0,
        temperature=0.0,
        max_tokens=200,
    )
    # Safely extract content with error handling
    choices = response.get("choices", [])
    if not choices or len(choices) == 0:
        logger.warning("image_search_no_choices", product=product_name)
        return f"https://cdn.comparoo.com/placeholder/{product_id}.png", "placeholder"
    
    message = choices[0].get("message", {})
    content = message.get("content", "{}") if message else "{}"
    if not content or content == "{}":
        logger.warning("image_search_empty_response", product=product_name)
        return f"https://cdn.comparoo.com/placeholder/{product_id}.png", "placeholder"
    
    content = _strip_json_fences(content)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("image_search_parse_failed", product=product_name, content=content[:200])
        return f"https://cdn.comparoo.com/placeholder/{product_id}.png", "placeholder"

    image_url = payload.get("image_url")
    image_source = payload.get("image_source")
    
    # Validate image_url - must be a valid HTTP/HTTPS URL
    if not image_url or not isinstance(image_url, str) or not image_url.strip():
        logger.warning("image_search_missing_url", product=product_name)
        return f"https://cdn.comparoo.com/placeholder/{product_id}.png", "placeholder"
    
    image_url = image_url.strip()
    if not (image_url.startswith("http://") or image_url.startswith("https://")):
        logger.warning("image_search_invalid_url", product=product_name, url=image_url)
        return f"https://cdn.comparoo.com/placeholder/{product_id}.png", "placeholder"
    
    proxied_url = _proxy_image_url(image_url)
    if proxied_url != image_url:
        logger.debug("image_search_proxied", product=product_name, original=image_url, proxied=proxied_url)
    return proxied_url, image_source


async def _run_product_research(
    *,
    settings: Settings,
    product: CandidateProduct,
    cached_product: ResearchProduct | None,
    glm_client: GlmClient,
    cache: RedisCache,
    theme: Sequence[str],
    semaphore: asyncio.Semaphore,
) -> tuple[ResearchProduct, int]:
    metrics_list = ", ".join(theme)
    primary_metric = theme[0] if theme else "performance"
    product_id = product.product_id or _generate_product_id(product.name, 0)
    user_prompt = (
        f"Product to research: {product.name}\n"
        f"Product ID: {product_id}\n"
        f"Comparison metrics: {metrics_list}\n"
        f"You have maximum {settings.b_search_budget_per_agent} searches.\n"
        "Return JSON per the specification in the system prompt."
    )

    system_prompt_research = (
        prompts.SYSTEM_PROMPT_B.replace("{product_name}", product.name).replace("{metric}", primary_metric)
    )
    response, search_steps = await glm_client.call(
        system_prompt=system_prompt_research,
        user_prompt=user_prompt,
        max_searches=settings.b_search_budget_per_agent,
        timeout_seconds=settings.glm_timeout_seconds or 8.0,
        temperature=0.1,
        max_tokens=2000,
    )
    # Safely extract content with error handling
    choices = response.get("choices", [])
    if not choices or len(choices) == 0:
        logger.error("glm_research_no_choices", product=product.name, response_keys=list(response.keys()))
        raise ValueError("Product research returned no choices in response")
    
    message = choices[0].get("message", {})
    if not message:
        logger.error("glm_research_no_message", product=product.name, choice=choices[0] if choices else None)
        raise ValueError("Product research returned no message in choice")
    
    content = message.get("content", "{}")
    if not content or content == "{}" or not content.strip():
        logger.error("glm_research_empty_response", product=product.name, finish_reason=choices[0].get("finish_reason"), response_keys=list(response.keys()))
        raise ValueError("Product research returned empty response")
    
    content = _strip_json_fences(content)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error("glm_research_parse_failed", product=product.name, content=content[:500], error=str(exc))
        raise ValueError("Product research output is not valid JSON") from exc

    title = payload.get("title") or product.name
    link = payload.get("link") or payload.get("purchase_link")
    if not link:
        raise ValueError("Product research did not return a purchase link.")
    price_cents, price_source = _extract_price_cents(payload, product.name)
    logger.debug(
        "price_parsed",
        product=product.name,
        price_cents=price_cents,
        price_source=price_source,
        price_raw=payload.get("price"),
    )
    if price_cents <= 0 and payload.get("price"):
        logger.warning(
            "price_fallback_zero",
            product=product.name,
            price_raw=payload.get("price"),
            price_display=payload.get("price_display"),
        )

    image_url = payload.get("image_url")
    image_source = payload.get("image_source")
    image_search_attempted = False
    # Validate image_url - must be a non-empty string that looks like a URL
    if not image_url or not isinstance(image_url, str) or not image_url.strip() or not (image_url.startswith("http://") or image_url.startswith("https://")):
        logger.info("image_url_missing_or_invalid", product=product.name, image_url=image_url)
        og_image = await _fetch_open_graph_image(link)
        if og_image:
            image_url = og_image
            image_source = "open_graph"
        elif settings.image_search_enabled:
            try:
                image_url, image_source = await _run_image_search(
                    glm_client=glm_client,
                    product_name=product.name,
                    product_id=product_id,
                    settings=settings,
                )
                search_steps += 1
                image_search_attempted = True
            except Exception as exc:
                logger.warning("image_search_failed", product=product.name, error=str(exc))
                image_url = f"https://cdn.comparoo.com/placeholder/{product_id}.png"
                image_source = "placeholder"
        else:
            image_url = f"https://cdn.comparoo.com/placeholder/{product_id}.png"
            image_source = "placeholder"
            logger.debug("image_search_skipped", product=product.name, reason="disabled")

    description = payload.get("summary") or payload.get("description") or ""
    pros = payload.get("pros") or []
    cons = payload.get("cons") or []
    full_review = payload.get("full_review") or ""
    review_url = payload.get("review_url")
    rating = payload.get("rating")
    extraction_confidence = payload.get("extraction_confidence") or payload.get("confidence") or "medium"
    is_affiliate = bool(payload.get("is_affiliate", False))

    # Ensure image_url is always a valid URL
    if not image_url or not isinstance(image_url, str) or not image_url.strip():
        image_url = f"https://cdn.comparoo.com/placeholder/{product_id}.png"
        image_source = image_source or "placeholder"
    elif not (image_url.startswith("http://") or image_url.startswith("https://")):
        image_url = f"https://cdn.comparoo.com/placeholder/{product_id}.png"
        image_source = image_source or "placeholder"
    else:
        proxied_url = _proxy_image_url(image_url)
        if proxied_url != image_url:
            logger.debug("image_url_proxied", product=product.name, original=image_url, proxied=proxied_url)
            image_url = proxied_url
            if not image_source:
                image_source = "proxied"

    if image_search_attempted:
        logger.debug(
            "image_search_attempted",
            product=product.name,
            image_source=image_source,
        )

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
        price_cents=price_cents or None,
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
    settings: Settings,
    products: Sequence[CandidateProduct],
    glm_client: GlmClient,
    cache: RedisCache,
    metrics: Sequence[str],
    use_cache: bool = True,
) -> StepOutcome[list[ResearchProduct]]:
    """Run GLM Agent B in parallel to gather structured product data."""

    if not products:
        return StepOutcome(data=[], api_calls=0, metadata={"searches_used": 0, "failures": 0})

    semaphore = asyncio.Semaphore(settings.extraction_max_concurrency)
    successes: list[ResearchProduct] = []
    failures: list[dict[str, Any]] = []
    cache_hits = 0
    total_searches = 0
    worker_timings: list[dict[str, Any]] = []

    async def worker(candidate: CandidateProduct) -> None:
        nonlocal cache_hits, total_searches
        start_time = perf_counter()
        logger.debug("agent_b_worker_enqueued", product=candidate.name)

        if use_cache:
            cached = await _load_cached_research(cache=cache, product=candidate)
            if cached:
                cache_hits += 1
                successes.append(cached)
                worker_timings.append(
                    {
                        "product": candidate.name,
                        "duration_ms": 0.0,
                        "wait_ms": (perf_counter() - start_time) * 1000,
                        "searches": 0,
                        "from_cache": True,
                    }
                )
                logger.debug(
                    "agent_b_worker_cache_hit",
                    product=candidate.name,
                    wait_ms=(perf_counter() - start_time) * 1000,
                )
                return

        async with semaphore:
            acquired_time = perf_counter()
            wait_ms = (acquired_time - start_time) * 1000
            in_flight = settings.extraction_max_concurrency - semaphore._value
            logger.debug(
                "agent_b_worker_started",
                product=candidate.name,
                wait_ms=wait_ms,
                in_flight=in_flight,
                concurrency_limit=settings.extraction_max_concurrency,
            )

            searches = 0
            try:
                research, searches = await _run_product_research(
                    settings=settings,
                    product=candidate,
                    cached_product=None,
                    glm_client=glm_client,
                    cache=cache,
                    theme=metrics,
                    semaphore=semaphore,
                )
                duration_ms = (perf_counter() - acquired_time) * 1000
                total_searches += searches
                await _store_cached_research(
                    cache=cache,
                    product=candidate,
                    research=research,
                    settings=settings,
                )
                successes.append(research)
                worker_timings.append(
                    {
                        "product": candidate.name,
                        "duration_ms": duration_ms,
                        "wait_ms": wait_ms,
                        "searches": searches,
                        "from_cache": False,
                    }
                )
                logger.info(
                    "agent_b_worker_completed",
                    product=candidate.name,
                    duration_ms=duration_ms,
                    wait_ms=wait_ms,
                    searches=searches,
                )
            except Exception as exc:
                duration_ms = (perf_counter() - acquired_time) * 1000
                logger.exception(
                    "product_research_failed",
                    product=candidate.name,
                    error=str(exc),
                    duration_ms=duration_ms,
                    wait_ms=wait_ms,
                )
                failures.append({"product": candidate, "error": str(exc)})
                worker_timings.append(
                    {
                        "product": candidate.name,
                        "duration_ms": duration_ms,
                        "wait_ms": wait_ms,
                        "searches": searches,
                        "from_cache": False,
                        "error": str(exc),
                    }
                )
            finally:
                total_ms = (perf_counter() - start_time) * 1000
                logger.debug(
                    "agent_b_worker_finished",
                    product=candidate.name,
                    total_ms=total_ms,
                    searches=searches,
                )

    await asyncio.gather(*(worker(product) for product in products))

    metadata = {
        "searches_used": total_searches,
        "cache_hits": cache_hits,
        "failures": [
            {"product": failure["product"].name, "error": failure["error"]} for failure in failures
        ],
        "worker_timings": worker_timings,
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
    settings: Settings,
    theme: Sequence[str],
    research: Sequence[ResearchProduct],
    glm_client: GlmClient,
) -> StepOutcome[ComparisonPayload]:
    """Use GLM Agent C to rank products, assign star ratings, and build comparison table."""

    if not research:
        raise ValueError("No product research data available for comparison.")

    reviews_text = ""
    for product in research:
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
        f"Comparison metrics: {', '.join(theme)}\n"
        f"Return JSON per the required structure."
    )

    response, _ = await glm_client.call(
        system_prompt=prompts.SYSTEM_PROMPT_C,
        user_prompt=user_prompt,
        max_searches=0,  # No searches needed for comparison synthesis
        timeout_seconds=settings.glm_timeout_seconds or 8.0,
        temperature=0.4,
        max_tokens=2000,
    )
    # Safely extract content with error handling
    choices = response.get("choices", [])
    if not choices or len(choices) == 0:
        logger.error("comparison_no_choices", response_keys=list(response.keys()))
        raise ValueError("Comparison returned no choices in response")
    
    message = choices[0].get("message", {})
    if not message:
        logger.error("comparison_no_message", choice=choices[0] if choices else None)
        raise ValueError("Comparison returned no message in choice")
    
    content = message.get("content", "{}")
    if not content or content == "{}" or not content.strip():
        logger.error("comparison_empty_response", finish_reason=choices[0].get("finish_reason"))
        raise ValueError("Comparison returned empty response")
    
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.exception("comparison_parse_failed", content=content)
        raise ValueError("Comparison synthesis output is not valid JSON") from exc

    table = _build_metric_comparison_table(payload)
    rankings = payload.get("rankings") or []
    summary_text = payload.get("summary") or ""

    id_to_product_name = {
        product.extraction.product_id: product.title for product in research
    }

    for row in table.rows:
        if row:
            candidate = row[0]
            display = id_to_product_name.get(candidate)
            if display:
                row[0] = display

    ordered_products: list[DisplayProduct] = []
    narratives: list[str] = []
    for entry in rankings:
        product = _match_research_product(entry, research)
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
                price_cents=product.price_cents or None,
                strengths=product.pros,
                weaknesses=product.cons,
                summary=product.summary,
                full_review=product.full_review,
                price_display=_format_price_cents(product.price_cents),
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
    "glm_discovery",
]

