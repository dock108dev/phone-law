import type { DemoPrincipal } from "./types";

const apiBase: string = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiRequestError extends Error {
  status: number;
  correlationId: string | null;

  constructor(message: string, status: number, correlationId: string | null) {
    super(message);
    this.status = status;
    this.correlationId = correlationId;
  }
}

export async function apiRequest<T>(
  path: string,
  principal: DemoPrincipal,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("X-Demo-Principal", principal);

  let response: Response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });
  } catch {
    throw new ApiRequestError(
      "The local service could not be reached. Check local system status and try again.",
      0,
      null,
    );
  }
  let text: string;
  try {
    text = await response.text();
  } catch {
    throw new ApiRequestError(
      "The service response was interrupted. Check the saved state before retrying.",
      response.status,
      response.headers.get("X-Correlation-ID"),
    );
  }
  let payload: { detail?: { error?: string; correlation_id?: string } } = {};
  if (!text && response.ok) {
    throw new ApiRequestError("The service returned an empty response.", response.status, response.headers.get("X-Correlation-ID"));
  }
  if (text) {
    try {
      const parsed: unknown = JSON.parse(text);
      if (parsed === null || typeof parsed !== "object") throw new Error("invalid_response");
      payload = parsed;
    } catch {
      throw new ApiRequestError(
        `The ${path.split("/").filter(Boolean)[1] ?? "requested"} service returned an unexpected response.`,
        response.status,
        response.headers.get("X-Correlation-ID"),
      );
    }
  }
  if (!response.ok) {
    throw new ApiRequestError(
      payload.detail?.error ?? "The synthetic review request could not be completed.",
      response.status,
      payload.detail?.correlation_id ?? response.headers.get("X-Correlation-ID"),
    );
  }
  return payload as T;
}
