/**
 * Root proxy (Next.js 16 convention — `middleware.ts` is deprecated).
 * Refreshes the Supabase session on every app request; skips static assets.
 */
import type { NextRequest } from "next/server";
import { updateSession } from "./lib/supabase/proxy";

export async function proxy(request: NextRequest) {
  return updateSession(request);
}

export const config = {
  matcher: [
    /*
     * Match all paths except static files, image optimization, and
     * public assets — auth logic must never block CSS/JS/images.
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
