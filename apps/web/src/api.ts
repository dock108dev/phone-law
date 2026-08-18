import type { DemoPrincipal } from "./types";

const apiBase: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:18000";

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
  headers.set("Content-Type", "application/json");
  headers.set("X-Demo-Principal", principal);

  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  const payload = (await response.json()) as {
    detail?: { error?: string; correlation_id?: string };
  };
  if (!response.ok) {
    throw new ApiRequestError(
      payload.detail?.error ?? "The synthetic review request could not be completed.",
      response.status,
      payload.detail?.correlation_id ?? response.headers.get("X-Correlation-ID"),
    );
  }
  return payload as T;
}
