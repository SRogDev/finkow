/**
 * Supabase env detection.
 *
 * The app builds and runs WITHOUT Supabase configured: auth is then
 * gracefully disabled (everyone sees the app, /login redirects home).
 * Check the cheap sync `isSupabaseConfigured()` before doing any async
 * Supabase work (Vercel rule: async-cheap-condition-before-await).
 */

export interface SupabaseEnv {
  url: string | null;
  anonKey: string | null;
}

function clean(value: string | undefined): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

/** Raw (possibly null) env values, trimmed. Never throws. */
export function supabaseEnv(): SupabaseEnv {
  return {
    url: clean(process.env.NEXT_PUBLIC_SUPABASE_URL),
    anonKey: clean(process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY),
  };
}

/** True only when both public Supabase vars are present and non-blank. */
export function isSupabaseConfigured(): boolean {
  const { url, anonKey } = supabaseEnv();
  return url !== null && anonKey !== null;
}
