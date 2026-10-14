/**
 * API client for communicating with the MAHALO3 backend.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8008";

interface ApiResponse<T> {
  data: T | null;
  error: string | null;
}

function normalizeErrorMessage(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }

  if (Array.isArray(value)) {
    return value
      .map((item) => normalizeErrorMessage(item))
      .filter(Boolean)
      .join("; ");
  }

  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const candidate = record.msg ?? record.message ?? record.detail;
    if (candidate) {
      return normalizeErrorMessage(candidate);
    }

    try {
      return JSON.stringify(value);
    } catch {
      return "Request failed";
    }
  }

  return "Request failed";
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  try {
    const url = `${API_BASE_URL}${endpoint}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((options.headers as Record<string, string>) || {}),
    };

    // Add auth token if available
    if (typeof window !== "undefined") {
      const token = sessionStorage.getItem("mahalo3_token");
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMessage =
        normalizeErrorMessage(errorData.detail) ||
        normalizeErrorMessage(errorData.message) ||
        `Request failed with status ${response.status}`;

      return {
        data: null,
        error: errorMessage,
      };
    }

    const data = await response.json();
    return { data, error: null };
  } catch (err) {
    return {
      data: null,
      error: err instanceof Error ? err.message : "An unknown error occurred",
    };
  }
}

export const api = {
  get: <T>(endpoint: string) => request<T>(endpoint, { method: "GET" }),
  post: <T>(endpoint: string, body: unknown) =>
    request<T>(endpoint, { method: "POST", body: JSON.stringify(body) }),
  put: <T>(endpoint: string, body: unknown) =>
    request<T>(endpoint, { method: "PUT", body: JSON.stringify(body) }),
  delete: <T>(endpoint: string) => request<T>(endpoint, { method: "DELETE" }),
};

export type { ApiResponse };
export { API_BASE_URL };
