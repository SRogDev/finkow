/**
 * Server Supabase client (official @supabase/ssr template pattern).
 *
 * Returns null when Supabase is not configured — auth is then gracefully
 * disabled and `getSessionUser()` resolves to null. Never throws for a
 * missing configuration; only for real client failures.
 */
import { createServerClient } from "@supabase/ssr";
import type { User } from "@supabase/supabase-js";
import { cookies } from "next/headers";
import { isSupabaseConfigured, supabaseEnv } from "./env";

export async function createClient() {
  if (!isSupabaseConfigured()) return null;
  const { url, anonKey } = supabaseEnv();
  const cookieStore = await cookies();
  // Checked non-null by isSupabaseConfigured() above.
  return createServerClient(url as string, anonKey as string, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          // Called from a Server Component where cookies are read-only.
          // The proxy refreshes the session instead.
        }
      },
    },
  });
}

/**
 * The currently signed-in user, or null when anonymous / unconfigured.
 * Cheap sync config check runs before any async work.
 */
export async function getSessionUser(): Promise<User | null> {
  if (!isSupabaseConfigured()) return null;
  const supabase = await createClient();
  if (!supabase) return null;
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return user;
}
