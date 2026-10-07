import { redirect } from "next/navigation";
import { HomeApp } from "@/components/HomeApp";
import { isSupabaseConfigured } from "@/lib/supabase/env";
import { getSessionUser } from "@/lib/supabase/server";

/**
 * Home gate (server component).
 *
 * When Supabase is configured, the proxy already redirects anonymous
 * visitors to /login — this is defense in depth for direct renders.
 * When Supabase is NOT configured, auth is gracefully disabled and
 * everyone sees the app (the pre-auth behavior).
 */
export default async function HomePage() {
  if (isSupabaseConfigured() && !(await getSessionUser())) {
    redirect("/login");
  }
  return <HomeApp />;
}
