/**
 * Auth input validation at the boundary (Vercel rule: server-auth-actions).
 * Pure functions — unit-tested. Returns an error message or null when valid.
 */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_EMAIL_LENGTH = 254;
const MIN_PASSWORD_LENGTH = 8;

export function validateEmail(raw: string): string | null {
  const email = raw.trim();
  if (!email) return "Enter your email address.";
  if (email.length > MAX_EMAIL_LENGTH || !EMAIL_RE.test(email)) {
    return "That email address doesn't look right.";
  }
  return null;
}

export function validatePassword(raw: string): string | null {
  if (!raw) return "Enter your password.";
  if (raw.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  return null;
}
