import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { resolveApiBase } from "./api.ts";

describe("resolveApiBase", () => {
  it("prefers the canonical FINKOW_API_URL", () => {
    assert.equal(
      resolveApiBase("http://api:8001", "http://legacy:8000"),
      "http://api:8001",
    );
  });

  it("falls back to the legacy API_URL alias", () => {
    assert.equal(resolveApiBase(undefined, "http://legacy:8000"), "http://legacy:8000");
  });

  it("defaults to localhost:8000 when nothing is set", () => {
    assert.equal(resolveApiBase(undefined, undefined), "http://localhost:8000");
  });
});
