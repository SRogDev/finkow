import assert from "node:assert/strict";
import { test } from "node:test";
import { validateEmail, validatePassword } from "./validation.ts";

test("validateEmail accepts a normal address", () => {
  assert.equal(validateEmail("ada@goldmine.dev"), null);
});

test("validateEmail trims surrounding whitespace", () => {
  assert.equal(validateEmail("  ada@goldmine.dev  "), null);
});

test("validateEmail rejects missing @", () => {
  assert.match(validateEmail("adagoldmine.dev") ?? "", /email/i);
});

test("validateEmail rejects empty input", () => {
  assert.match(validateEmail("   ") ?? "", /email/i);
});

test("validateEmail rejects overlong input", () => {
  assert.match(validateEmail(`${"a".repeat(300)}@x.dev`) ?? "", /email/i);
});

test("validatePassword accepts 8+ chars", () => {
  assert.equal(validatePassword("goldmine1"), null);
});

test("validatePassword rejects short passwords", () => {
  assert.match(validatePassword("short") ?? "", /8 characters/i);
});

test("validatePassword rejects empty input", () => {
  assert.match(validatePassword("") ?? "", /password/i);
});
