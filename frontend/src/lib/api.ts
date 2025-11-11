type GlobalWithProcess = typeof globalThis & {
  process?: {
    env?: {
      NEXT_PUBLIC_API_URL?: string;
    };
  };
};

const API_BASE_URL =
  ((globalThis as GlobalWithProcess).process?.env?.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000");

export interface CompareProductsRequest {
  category: string;
  constraints?: string;
}

export interface ComparisonProduct {
  product_id: string;
  name: string;
  image_url: string;
  link: string;
  description: string;
  rating: string;
  strengths: string[];
  weaknesses: string[];
}

export interface ComparisonMetrics {
  category: string;
  metrics: string[];
}

export interface ComparisonMetricsTable {
  headers: string[];
  rows: string[][];
}

export interface ComparisonDetails {
  comparison_summary: string;
  full_comparison: string;
  metrics_table: ComparisonMetricsTable;
}

export interface ComparisonResponse {
  status: string;
  request: {
    category: string;
    constraints?: string;
  };
  metrics: ComparisonMetrics;
  products: ComparisonProduct[];
  comparison: ComparisonDetails;
  cache_hit: boolean;
}

export class ApiError extends Error {
  status?: number;
  details?: unknown;

  constructor(message: string, options?: { status?: number; details?: unknown }) {
    super(message);
    this.name = "ApiError";
    this.status = options?.status;
    this.details = options?.details;

    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

export async function compareProducts(
  category: string,
  constraints?: string
): Promise<ComparisonResponse> {
  const trimmedCategory = category.trim();
  const trimmedConstraints = constraints?.trim();

  if (!trimmedCategory) {
    throw new ApiError("Category is required to compare products.");
  }

  const payload: CompareProductsRequest = { category: trimmedCategory };
  if (trimmedConstraints) {
    payload.constraints = trimmedConstraints;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/compare`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    throw new ApiError(
      "Unable to reach the comparison service. Please check your connection and try again.",
      { details: error }
    );
  }

  const isJsonResponse =
    response.headers.get("content-type")?.includes("application/json") ?? false;
  const responseBody = isJsonResponse
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const messageFromBody =
      typeof responseBody === "string"
        ? responseBody
        : typeof responseBody === "object" && responseBody !== null
          ? (responseBody as { detail?: string; message?: string }).detail ??
            (responseBody as { detail?: string; message?: string }).message ??
            ""
          : "";

    const message =
      messageFromBody.trim().length > 0
        ? `Comparison request failed (${response.status}): ${messageFromBody}`
        : `Comparison request failed with status ${response.status}.`;

    throw new ApiError(message, {
      status: response.status,
      details: responseBody,
    });
  }

  return responseBody as ComparisonResponse;
}

