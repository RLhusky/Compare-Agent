// In Next.js, NEXT_PUBLIC_* variables are replaced at build time
// They're available directly via process.env in client components
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  price_cents?: number;
  summary?: string;
  full_review?: string;
  price_display?: string;
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

export function generateSessionId(): string {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
}

export interface ProgressUpdate {
  step: string;
  status: string;
  progress: number;
}

export function connectProgressWebSocket(
  sessionId: string,
  onProgress: (data: ProgressUpdate) => void
): () => void {
  const wsUrl = API_BASE_URL.replace(/^http/, "ws");
  const wsEndpoint = `${wsUrl}/ws/compare/${sessionId}`;
  
  console.log("Connecting to WebSocket:", wsEndpoint);
  
  try {
    const ws = new WebSocket(wsEndpoint);

    ws.onopen = () => {
      console.log("WebSocket connection opened");
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log("WebSocket message received:", data);
        onProgress(data);
      } catch (error) {
        console.error("Failed to parse WebSocket message:", error);
      }
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      // Don't throw, just log - WebSocket errors are expected if backend doesn't support it yet
    };

    ws.onclose = (event) => {
      console.log("WebSocket connection closed:", event.code, event.reason);
    };

    // Return cleanup function
    return () => {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    };
  } catch (error) {
    console.error("Failed to create WebSocket:", error);
    // Return a no-op cleanup function if WebSocket creation fails
    return () => {};
  }
}

export async function compareProducts(
  category: string,
  constraints?: string,
  sessionId?: string
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

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  
  if (sessionId) {
    headers["X-Session-Id"] = sessionId;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/compare`, {
      method: "POST",
      headers,
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

