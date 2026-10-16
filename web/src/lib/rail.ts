/**
 * Duplicate a list so an infinite marquee can loop seamlessly:
 * the track translates -50% and the second copy takes over exactly
 * where the first ended. Render the second copy with aria-hidden.
 */
export function duplicateForLoop<T>(items: readonly T[]): T[] {
  return [...items, ...items];
}
