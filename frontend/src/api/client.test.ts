import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./client";

function respondWith(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("returns the JSON body of successful responses", async () => {
    respondWith(200, { status: "ok", llm_providers: [], max_upload_size_mb: 50, dataset_ttl_hours: 24 });
    await expect(api.health()).resolves.toMatchObject({ status: "ok" });
  });

  it("turns error envelopes into ApiError", async () => {
    respondWith(503, { error: { code: "llm_unavailable", message: "The language model is busy." } });

    const error = await api
      .preview("abc", { kind: "regex_replace", instruction: "emails" })
      .catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 503, code: "llm_unavailable", message: "The language model is busy." });
  });

  it("reports network failures in plain language", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(api.getDataset("abc")).rejects.toMatchObject({ code: "network_error" });
  });

  it("sends previews as JSON to the dataset's endpoint", async () => {
    respondWith(200, {});
    const request = { kind: "normalize_values", column: "State", instruction: "abbreviations" } as const;
    await api.preview("d 1", request);

    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/datasets/d%201/preview/");
    expect(init).toMatchObject({ method: "POST", body: JSON.stringify(request) });
  });
});
