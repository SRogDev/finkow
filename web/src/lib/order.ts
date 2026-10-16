/** Order-form quantity validation. Quantity stays a decimal STRING end-to-end. */

export type QuantityResult = { ok: true; quantity: string } | { ok: false; error: string };

const QUANTITY_PATTERN = /^\d+(\.\d{1,8})?$/;

export function validateQuantity(input: string): QuantityResult {
  const quantity = input.trim();
  if (quantity === "") {
    return { ok: false, error: "Enter a quantity." };
  }
  if (!QUANTITY_PATTERN.test(quantity)) {
    return {
      ok: false,
      error: "Quantity must be a positive number with up to 8 decimals.",
    };
  }
  if (Number(quantity) <= 0) {
    return { ok: false, error: "Quantity must be greater than zero." };
  }
  return { ok: true, quantity };
}
