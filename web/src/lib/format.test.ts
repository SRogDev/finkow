import assert from "node:assert/strict";
import { test } from "node:test";
import {
  formatMoney,
  formatPercent,
  formatQuantity,
  formatSignedMoney,
  formatSignedPercent,
} from "./format.ts";

test("formatMoney renders USD with two decimals", () => {
  assert.equal(formatMoney("100000.00"), "$100,000.00");
  assert.equal(formatMoney("150"), "$150.00");
  assert.equal(formatMoney("0.3000"), "$0.30");
});

test("formatMoney handles missing values gracefully", () => {
  assert.equal(formatMoney(null), "—");
  assert.equal(formatMoney(undefined), "—");
  assert.equal(formatMoney("not-a-number"), "—");
});

test("formatSignedMoney prefixes sign", () => {
  assert.equal(formatSignedMoney("12.50"), "+$12.50");
  assert.equal(formatSignedMoney("-12.5"), "-$12.50");
  assert.equal(formatSignedMoney("0.00"), "$0.00");
});

test("formatPercent appends percent sign", () => {
  assert.equal(formatPercent("3.00"), "3.00%");
  assert.equal(formatPercent("-1.5"), "-1.50%");
  assert.equal(formatPercent(null), "—");
});

test("formatSignedPercent prefixes sign", () => {
  assert.equal(formatSignedPercent("3.00"), "+3.00%");
  assert.equal(formatSignedPercent("-1.25"), "-1.25%");
});

test("formatQuantity trims trailing zeros", () => {
  assert.equal(formatQuantity("10.0000"), "10");
  assert.equal(formatQuantity("0.3000"), "0.3");
  assert.equal(formatQuantity(null), "—");
});
