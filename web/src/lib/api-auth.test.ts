import assert from "node:assert/strict";
import { test } from "node:test";
import { mergeAuthHeaders } from "./api.ts";
import { getAccessToken } from "./auth/token.ts";

test("mergeAuthHeaders without a token sets only the JSON content type", () => {
  const headers = mergeAuthHeaders(undefined, null);
  const asRecord = Object.fromEntries(new Headers(headers as HeadersInit).entries());
  assert.equal(asRecord["content-type"], "application/json");
  assert.ok(!("authorization" in asRecord), "no Authorization header without a session");
});

test("mergeAuthHeaders attaches the Bearer token and preserves caller headers", () => {
  const headers = mergeAuthHeaders(
    { headers: { "idempotency-key": "abc-123" } },
    "session-token-xyz",
  );
  const asRecord = Object.fromEntries(new Headers(headers as HeadersInit).entries());
  assert.equal(asRecord.authorization, "Bearer session-token-xyz");
  assert.equal(asRecord["idempotency-key"], "abc-123");
  assert.equal(asRecord["content-type"], "application/json");
});

test("mergeAuthHeaders never invents a token", () => {
  const headers = mergeAuthHeaders({ headers: { authorization: "Bearer keep-me" } }, null);
  const asRecord = Object.fromEntries(new Headers(headers as HeadersInit).entries());
  assert.equal(asRecord.authorization, "Bearer keep-me");
});

test("getAccessToken returns null when Supabase is not configured", async () => {
  delete process.env.NEXT_PUBLIC_SUPABASE_URL;
  delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  assert.equal(await getAccessToken(), null);
});
