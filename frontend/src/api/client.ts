import type { ApplyRequest, Dataset, Preview, ReplacementRequest, RowsPage, ServerInfo } from "./types";

/** An error response from the API: `{"error": {"code", "message", "details"}}`. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const NETWORK_ERROR = "Could not reach the server. Check your connection and try again.";

export function toApiError(status: number, body: unknown): ApiError {
  const error = (body as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error;
  return new ApiError(
    status,
    error?.code ?? "http_error",
    error?.message ?? `The server responded with an error (HTTP ${status}).`,
    error?.details,
  );
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers: { Accept: "application/json", ...init.headers } });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "network_error", NETWORK_ERROR);
  }
  if (response.status === 204) return undefined as T;
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw toApiError(response.status, body);
  return body as T;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

const datasetPath = (id: string, suffix = "") => `/api/datasets/${encodeURIComponent(id)}/${suffix}`;

/** Upload with XMLHttpRequest, because fetch cannot report upload progress. */
function uploadDataset(file: File, onProgress?: (fraction: number) => void): Promise<Dataset> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/datasets/");
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total);
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        // not JSON; toApiError falls back to a generic message
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Dataset);
      else reject(toApiError(xhr.status, body));
    };
    xhr.onerror = () => reject(new ApiError(0, "network_error", NETWORK_ERROR));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

export const api = {
  health: () => request<ServerInfo>("/api/health/"),
  upload: uploadDataset,
  getDataset: (id: string) => request<Dataset>(datasetPath(id)),
  rows: (id: string, page: number, pageSize: number, signal?: AbortSignal) =>
    request<RowsPage>(`${datasetPath(id, "rows/")}?page=${page}&page_size=${pageSize}`, { signal }),
  preview: (id: string, body: ReplacementRequest) => postJson<Preview>(datasetPath(id, "preview/"), body),
  apply: (id: string, body: ApplyRequest) => postJson<Dataset>(datasetPath(id, "transformations/"), body),
  undo: (id: string) => request<Dataset>(datasetPath(id, "transformations/undo/"), { method: "POST" }),
  exportUrl: (id: string, fileType: "csv" | "xlsx") => `${datasetPath(id, "export/")}?file_type=${fileType}`,
};
