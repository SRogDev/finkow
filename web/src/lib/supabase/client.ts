/**
 * Browser Supabase client (official @supabase/ssr template pattern).
 *
 * Returns null when Supabase is not configured — the app then runs with
 * auth gracefully disabled. Callers must handle null (or check
 * isSupabaseConfigured() first).
 */
import { createBrowserClient } from "@supabase/ssr";
import { isSupabaseConfigured, supabaseEnv } from "./env";

export function createClient() {
  if (!isSupabaseConfigured()) return null;
  const { url, anonKey } = supabaseEnv();
  // Checked non-null by isSupabaseConfigured() above.
  return createBrowserClient(url as string, anonKey as string);
}
