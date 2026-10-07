import { redirect } from "next/navigation";
import { isSupabaseConfigured } from "@/lib/supabase/env";
import { getSessionUser } from "@/lib/supabase/server";
import { LoginForm } from "./LoginForm";

/**
 * The sign-in gate. Anonymous visitors land here (via the proxy);
 * signed-in users bounce straight to the app.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  // Auth disabled → the app is open to everyone; no gate to show.
  if (!isSupabaseConfigured()) {
    redirect("/");
  }
  const user = await getSessionUser();
  if (user) {
    redirect("/");
  }
  const { error } = await searchParams;
  return (
    <div className="py-10">
      <LoginForm authError={error} />
    </div>
  );
}
