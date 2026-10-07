import { LogOut } from "lucide-react";
import { isSupabaseConfigured } from "@/lib/supabase/env";
import { getSessionUser } from "@/lib/supabase/server";

/**
 * Header auth slot (async server component — no client JS).
 * Renders nothing when auth is disabled; otherwise a sign-in link
 * for visitors or a sign-out form for members.
 */
export async function HeaderAuth() {
  if (!isSupabaseConfigured()) {
    return null;
  }
  const user = await getSessionUser();
  if (!user) {
    return (
      <a
        href="/login"
        className="inline-flex cursor-pointer items-center rounded-xl gold-bg px-4 py-2 text-sm font-semibold text-on-accent transition-all duration-200 hover:brightness-110"
      >
        Sign in
      </a>
    );
  }
  return (
    <form action="/auth/signout" method="post" className="flex items-center gap-3">
      <span className="hidden max-w-40 truncate text-xs text-muted-foreground sm:block">
        {user.email}
      </span>
      <button
        type="submit"
        className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-border px-3.5 py-2 text-sm font-medium text-foreground transition-colors duration-200 hover:border-accent/60 hover:text-accent"
      >
        <LogOut className="h-4 w-4" aria-hidden />
        Sign out
      </button>
    </form>
  );
}
