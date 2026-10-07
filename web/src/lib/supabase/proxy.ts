/**
 * Session refresh for the Next.js proxy (official @supabase/ssr template
 * pattern, adapted from middleware.ts → proxy.ts for Next.js 16).
 *
 * Refreshes the auth session on every matched request and redirects
 * anonymous visitors away from the app shell to /login.
 */
import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";
import { isSupabaseConfigured, supabaseEnv } from "./env";

export async function updateSession(request: NextRequest) {
  // Cheap sync check before any async work (Vercel: async-cheap-condition-before-await).
  if (!isSupabaseConfigured()) {
    return NextResponse.next({ request });
  }

  let supabaseResponse = NextResponse.next({ request });
  const { url, anonKey } = supabaseEnv();

  const supabase = createServerClient(url as string, anonKey as string, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        for (const { name, value } of cookiesToSet) {
          request.cookies.set(name, value);
        }
        supabaseResponse = NextResponse.next({ request });
        for (const { name, value, options } of cookiesToSet) {
          supabaseResponse.cookies.set(name, value, options);
        }
      },
    },
  });

  // Do not run code between createServerClient and getUser(): a simple
  // mistake here randomly logs users out and is hard to debug.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;
  const isAuthRoute = pathname.startsWith("/login") || pathname.startsWith("/auth");

  if (!user && !isAuthRoute) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  return supabaseResponse;
}
