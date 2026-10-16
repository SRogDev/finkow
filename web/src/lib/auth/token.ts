import { createClient } from "../supabase/client.ts";
import { isSupabaseConfigured } from "../supabase/env.ts";

/**
 * Supabase session access token for backend calls.
 *
 * Returns null when Supabase is not configured (auth gracefully disabled)
 * or when there is no signed-in session — the FastAPI backend then runs in
 * its own dev-mode (no token required). Never throws: a missing token is a
 * normal state, not an error.
 */
export async function getAccessToken(): Promise<string | null> {
  // Cheap sync check first (Vercel rule: async-cheap-condition-before-await).
  if (!isSupabaseConfigured()) return null;
  try {
    const supabase = createClient();
    if (!supabase) return null;
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  } catch {
    return null;
  }
}
