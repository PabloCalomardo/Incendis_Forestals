import type { ApiStatus, VersionResponse } from "@wip/shared-types";

const API_BASE_URL =
  typeof window === "undefined"
    ? (process.env.API_INTERNAL_BASE_URL ??
      process.env.NEXT_PUBLIC_API_BASE_URL ??
      "http://localhost:8000")
    : (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000");

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Accept: "application/json",
    },
    next: {
      revalidate: 15,
    },
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function getApiStatus(): Promise<ApiStatus> {
  try {
    const version = await request<VersionResponse>("/version");
    return { ok: true, version: version.version };
  } catch {
    return { ok: false };
  }
}
