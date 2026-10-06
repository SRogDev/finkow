import assert from "node:assert/strict";
import { test } from "node:test";
import { duplicateForLoop } from "./rail.ts";

test("duplicateForLoop doubles the list preserving order", () => {
  const doubled = duplicateForLoop(["a", "b", "c"]);
  assert.deepEqual(doubled, ["a", "b", "c", "a", "b", "c"]);
});

test("duplicateForLoop handles an empty list", () => {
  assert.deepEqual(duplicateForLoop([]), []);
});

test("duplicateForLoop does not mutate the input", () => {
  const items = ["a", "b"];
  duplicateForLoop(items);
  assert.deepEqual(items, ["a", "b"]);
});
