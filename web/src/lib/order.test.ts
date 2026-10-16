import assert from "node:assert/strict";
import { test } from "node:test";
import { validateQuantity } from "./order.ts";

test("validateQuantity accepts positive integers and decimals", () => {
  assert.deepEqual(validateQuantity("10"), { ok: true, quantity: "10" });
  assert.deepEqual(validateQuantity("0.5"), { ok: true, quantity: "0.5" });
  assert.deepEqual(validateQuantity("1.12345678"), {
    ok: true,
    quantity: "1.12345678",
  });
});

test("validateQuantity rejects zero, negatives and garbage", () => {
  assert.equal(validateQuantity("0").ok, false);
  assert.equal(validateQuantity("-5").ok, false);
  assert.equal(validateQuantity("abc").ok, false);
  assert.equal(validateQuantity("").ok, false);
  assert.equal(validateQuantity("   ").ok, false);
});

test("validateQuantity rejects more than 8 decimals", () => {
  assert.equal(validateQuantity("1.123456789").ok, false);
});

test("validateQuantity trims surrounding whitespace", () => {
  assert.deepEqual(validateQuantity("  10  "), { ok: true, quantity: "10" });
});
