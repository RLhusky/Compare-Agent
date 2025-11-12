"""Pydantic schemas for the product comparison workflow."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, Field, computed_field


class CompareRequest(BaseModel):
    """Incoming request payload for `/api/compare`."""

    category: str = Field(..., min_length=2, max_length=120)
    constraints: str | None = Field(default=None, max_length=512)
    use_cache: bool = Field(default=True)


class MetricsResult(BaseModel):
    """Comparison metrics returned by Step 1."""

    category: str
    metrics: list[str]
    cached: bool = False
    cached_at: datetime | None = None


class CandidateProduct(BaseModel):
    """Product discovered from Step 2/3 searches."""

    product_id: str | None = None
    name: str
    source: str | None = None
    source_url: AnyHttpUrl | None = None
    discovery_method: Literal[
        "ranking_site",
        "best_sellers",
        "amazon_top_rated",
        "reddit_recommendations",
        "forum_recommendations",
        "sonar_a1",
    ] | None = None
    confidence: Literal["high", "medium", "low"] | None = None


class MetricComparison(BaseModel):
    """Tabular representation for frontend display."""

    headers: list[str]
    rows: list[list[str]]


class ProductStrengthsWeaknesses(BaseModel):
    """Strengths and weaknesses extracted from analysis."""

    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


class ComparisonPayload(BaseModel):
    """Comparison analysis payload returned to the frontend."""

    comparison_summary: str
    full_comparison: str
    products: list["DisplayProduct"]
    metrics_table: MetricComparison


class WorkflowStats(BaseModel):
    """Diagnostics for monitoring and debugging."""

    api_calls: int = 0
    duration_seconds: float = 0.0
    used_fallback: bool = False
    source_summary: dict[str, int] = Field(default_factory=dict)
    extraction_metrics: dict[str, Any] = Field(default_factory=dict)


class ComparisonResponse(BaseModel):
    """HTTP response combining payload and metadata."""

    request: CompareRequest
    metrics: MetricsResult
    products: list["DisplayProduct"]
    comparison: ComparisonPayload
    stats: WorkflowStats
    cached_result: bool = False
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    @computed_field  # type: ignore[misc]
    @property
    def product_count(self) -> int:
        return len(self.products)


class ProductExtraction(BaseModel):
    """Structured product data produced in Step 4."""

    product_id: str | None = None
    name: str
    image_url: AnyHttpUrl
    link: AnyHttpUrl
    is_affiliate: bool = False
    description: str
    rating: str | None = None
    review_url: AnyHttpUrl | None = None
    extraction_confidence: Literal["high", "medium", "low"] = "medium"
    price_cents: int | None = None


class DisplayProduct(ProductExtraction):
    """Product payload returned to the frontend (includes highlights)."""

    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    summary: str | None = None
    full_review: str | None = None
    price_display: str | None = None


ComparisonPayload.model_rebuild()
ComparisonResponse.model_rebuild()
