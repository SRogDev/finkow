"use server";

import { revalidatePath } from "next/cache";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { validateEmail, validatePassword } from "@/lib/auth/validation";
import { isSupabaseConfigured } from "@/lib/supabase/env";
import { createClient } from "@/lib/supabase/server";

/**
 * Server actions for sign-in (Vercel rule: server-auth-actions — validate
 * every input at the boundary, never trust the form).
 */

export interface AuthState {
  ok: boolean;
  error: string | null;
  notice: string | null;
}

const INITIAL: AuthState = { ok: false, error: null, notice: null };

function authDisabled(): AuthState {
  return { ...INITIAL, error: "Sign-in is not configured yet." };
}

/** Map Supabase's English errors to plain-language messages. */
function friendlyError(message: string): string {
  if (/invalid login credentials/i.test(message)) {
    return "Wrong email or password. Try again.";
  }
  if (/email not confirmed/i.test(message)) {
    return "Check your inbox to confirm your email first.";
  }
  if (/user already registered/i.test(message)) {
    return "This email already has an account — sign in instead.";
  }
  if (/password.*weak|weak.*password/i.test(message)) {
    return "That password is too weak — make it longer.";
  }
  return "Something went wrong signing you in. Try again.";
}

function siteUrl(): Promise<string> {
  return headers().then((h) => {
    const proto = h.get("x-forwarded-proto") ?? "http";
    const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3000";
    return `${proto}://${host}`;
  });
}

/** Email + password sign in. Redirects home on success (redirect throws). */
export async function login(formData: FormData): Promise<AuthState> {
  if (!isSupabaseConfigured()) return authDisabled();
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");

  const emailError = validateEmail(email);
  if (emailError) return { ...INITIAL, error: emailError };
  const passwordError = validatePassword(password);
  if (passwordError) return { ...INITIAL, error: passwordError };

  const supabase = await createClient();
  if (!supabase) return authDisabled();

  const { error } = await supabase.auth.signInWithPassword({
    email: email.trim(),
    password,
  });
  if (error) return { ...INITIAL, error: friendlyError(error.message) };

  revalidatePath("/", "layout");
  redirect("/");
}

/** Email + password sign up. May need email confirmation first. */
export async function signup(formData: FormData): Promise<AuthState> {
  if (!isSupabaseConfigured()) return authDisabled();
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");

  const emailError = validateEmail(email);
  if (emailError) return { ...INITIAL, error: emailError };
  const passwordError = validatePassword(password);
  if (passwordError) return { ...INITIAL, error: passwordError };

  const supabase = await createClient();
  if (!supabase) return authDisabled();

  const { data, error } = await supabase.auth.signUp({
    email: email.trim(),
    password,
    options: { emailRedirectTo: `${await siteUrl()}/auth/callback` },
  });
  if (error) return { ...INITIAL, error: friendlyError(error.message) };

  if (data.session) {
    revalidatePath("/", "layout");
    redirect("/");
  }
  return {
    ok: true,
    error: null,
    notice: "Check your inbox to confirm your account, then sign in.",
  };
}

/** Passwordless magic link via email. */
export async function sendMagicLink(formData: FormData): Promise<AuthState> {
  if (!isSupabaseConfigured()) return authDisabled();
  const email = String(formData.get("email") ?? "");

  const emailError = validateEmail(email);
  if (emailError) return { ...INITIAL, error: emailError };

  const supabase = await createClient();
  if (!supabase) return authDisabled();

  const { error } = await supabase.auth.signInWithOtp({
    email: email.trim(),
    options: { emailRedirectTo: `${await siteUrl()}/auth/callback` },
  });
  if (error) return { ...INITIAL, error: friendlyError(error.message) };

  return {
    ok: true,
    error: null,
    notice: "Check your inbox — your sign-in link is on its way.",
  };
}

export { INITIAL as INITIAL_AUTH_STATE };
