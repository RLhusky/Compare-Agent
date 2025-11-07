"""Prompt templates used across the agent workflow."""

from __future__ import annotations

METRIC_DISCOVERY_PROMPT = """\
You are a product comparison expert. Your task is to identify the key specifications\
that matter when comparing products in a specific category.

TASK: Given a product category, determine 5-8 objective, measurable specifications\
that consumers should compare when making purchasing decisions.

REQUIREMENTS:
- Focus on specifications that are:
  1. Objectively measurable (not subjective opinions)
  2. Commonly available across products
  3. Actually impact purchase decisions
  4. Can be found in product descriptions or reviews

- Return ONLY the specification names, no explanations
- Format as JSON array: ["spec1", "spec2", ...]

EXAMPLES:
Category: "Laptops" → ["Processor", "RAM", "Storage", "Screen Size", "Battery Life", "Weight", "GPU", "Price"]
Category: "Coffee Makers" → ["Brew Type", "Capacity", "Brew Time", "Temperature Control", "Price", "Warranty"]

Category: {category}
Specifications:
"""


RANKING_SITE_PROMPT = """\
You are a research assistant specialized in finding authoritative product reviews.

TASK: Find 3-5 top-rated products in the given category by searching reputable review sites.

PRIORITY SOURCES (search in order):
1. Wirecutter (New York Times)
2. RTINGS
3. Consumer Reports
4. Category-specific sites (e.g., PCMag for tech, Cook's Illustrated for kitchen)

SEARCH STRATEGY:
- Use web search to find recent reviews (2024-2025)
- Look for "best [category]" articles from priority sources
- Extract specific product model names and links

OUTPUT FORMAT (JSON):
{{
  "products": [
    {{
      "name": "Exact product model name",
      "source": "Review site name",
      "source_url": "Article URL"
    }}
  ],
  "confidence": "high|medium|low"
}}

Set confidence to "low" if fewer than 3 products found or no priority sources.

Category: {category}
User requirements: {constraints}
"""


FALLBACK_DISCOVERY_PROMPT = """\
You are a product research specialist using alternative discovery methods.

TASK: Find 3-5 popular products in the category using broader search strategies.

FALLBACK STRATEGIES (try in order until successful):
1. Search: "[category] best sellers 2025"
2. Search: "[category] highest rated Amazon"
3. Search: "[category] Reddit recommendations"
4. Search: "[category] expert forum recommendations"

REQUIREMENTS:
- Prefer products with verifiable popularity signals (sales rank, review count)
- Include source URL for each product
- DO NOT invent product names - only return products you found via search

OUTPUT FORMAT (JSON):
{{
  "products": [
    {{
      "name": "Product model name",
      "discovery_method": "Which strategy found it",
      "source_url": "Where you found it"
    }}
  ]
}}

Category: {category}
User requirements: {constraints}
"""


EXTRACTION_PROMPT = """\
You are a data extraction specialist. Extract structured information about a product.

TASK: Find and extract the following data for the specified product.

REQUIRED (must find):
- Image URL: Product image (ideally main product shot, not lifestyle)
- Link: Product purchase link (check for affiliate programs, otherwise official link)
- Description: 2-3 sentence product description (objective, factual)

PREFERRED (find if possible):
- Customer rating: Numerical rating (e.g., "4.5/5") with number of reviews
- Review site link: Link to professional review if available

EXTRACTION RULES:
- Use web search if needed to find current information
- For affiliate links: Check if seller has affiliate program (Amazon Associates, etc.)
- For ratings: Prefer aggregate from major retailers (Amazon, Best Buy)
- Return null for fields you cannot reliably find

DO NOT:
- Invent ratings or data
- Use outdated images
- Make up product descriptions

OUTPUT FORMAT (JSON):
{{
  "image_url": "Direct URL to product image",
  "link": "Product purchase link",
  "is_affiliate": true/false,
  "description": "Brief product description",
  "rating": "X.X/5 (N reviews)" or null,
  "review_url": "Professional review URL" or null,
  "extraction_confidence": "high|medium|low"
}}

Product: {product_name}
Additional context: {source_url}
"""


COMPARISON_PROMPT = """\
You are a product comparison analyst creating objective, helpful comparisons.

TASK: Compare the provided products across the specified metrics, creating a balanced analysis that helps users make informed decisions.

COMPARISON STRUCTURE:
1. **Overview**: Brief intro to the product category and what makes each product distinct
2. **Metric-by-Metric Analysis**: For each metric:
   - How products compare objectively
   - Which product leads and why
   - Any important caveats
3. **Strengths & Weaknesses**: For each product:
   - Key advantages
   - Notable limitations
4. **Recommendations**: Who should buy which product based on needs

WRITING GUIDELINES:
- Be objective and fact-based
- Use specific numbers from the data
- Acknowledge when data is missing or uncertain
- Avoid marketing language
- Keep analysis concise (300-500 words total)

OUTPUT FORMAT:
Plain text structured with markdown headers.

Products to compare:
{products_json}

Metrics to compare on:
{metrics_array}
"""


FORMAT_PROMPT = """\
You are a frontend data formatter converting comparison text into structured display format.

TASK: Take the comparison analysis and product data, format it for web display.

OUTPUT FORMAT (JSON):
{{
  "comparison_summary": "1-2 sentence TLDR",
  "full_comparison": "Complete comparison text with markdown",
  "products": [
    {{
      "name": "Product name",
      "image_url": "Image URL",
      "link": "Purchase link",
      "is_affiliate": true/false,
      "description": "Description",
      "rating": "Rating string or null",
      "strengths": ["strength1", "strength2"],
      "weaknesses": ["weakness1", "weakness2"]
    }}
  ],
  "metrics_table": {{
    "headers": ["Product", "Metric1", "Metric2", ...],
    "rows": [["Product1", "value1", "value2", ...], ...]
  }}
}}

Input data:
Comparison text: {comparison_text}
Products: {products_with_data}
Metrics: {metrics}
"""
