"use client";

import { Coins, Mail } from "lucide-react";
import { useActionState, useState } from "react";
import { GoldButton, TypingDots } from "@/components/ui";
import { type AuthState, INITIAL_AUTH_STATE, login, sendMagicLink, signup } from "./actions";

const inputClass =
  "w-full rounded-xl border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/60 transition-colors duration-200 focus:border-accent focus:outline-none disabled:opacity-60";

/**
 * The sign-in gate: email+password (sign in / create account) and
 * passwordless magic link. Gold premium look, zero jargon.
 */
export function LoginForm({ authError }: { authError?: string }) {
  const [mode, setMode] = useState<"login" | "signup">("login");

  const [state, formAction, pending] = useActionState(
    async (_prev: AuthState, formData: FormData): Promise<AuthState> => {
      return mode === "signup" ? signup(formData) : login(formData);
    },
    INITIAL_AUTH_STATE,
  );

  const [linkState, linkAction, linkPending] = useActionState(
    async (_prev: AuthState, formData: FormData): Promise<AuthState> => sendMagicLink(formData),
    INITIAL_AUTH_STATE,
  );

  const shownError =
    state.error ??
    (authError === "auth-code-error" ? "That sign-in link expired. Try again." : null);

  return (
    <div className="mx-auto w-full max-w-md">
      <div className="mb-8 text-center">
        <span className="btn-sheen mx-auto flex h-14 w-14 items-center justify-center rounded-2xl gold-bg shadow-[0_10px_36px_-8px_rgba(245,158,11,0.55)]">
          <Coins className="h-7 w-7 text-on-accent" aria-hidden />
        </span>
        <p className="mt-5 text-xs font-semibold uppercase tracking-[0.18em] text-accent">
          Welcome to your gold mine
        </p>
        <h1 className="font-display mt-2 text-3xl font-semibold tracking-tight text-foreground">
          Sign in to Finkow
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Your AI investing agents are waiting. No jargon, no brokerage apps.
        </p>
      </div>

      <div className="rounded-2xl border border-border bg-card p-6 sm:p-8">
        <div
          className="mb-6 grid grid-cols-2 rounded-xl bg-muted/60 p-1"
          role="tablist"
          aria-label="Sign in or create account"
        >
          {(["login", "signup"] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              onClick={() => setMode(m)}
              className={`cursor-pointer rounded-lg px-4 py-2 text-sm font-semibold transition-all duration-200 ${
                mode === m
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {m === "login" ? "Sign in" : "Create account"}
            </button>
          ))}
        </div>

        <form action={formAction} className="flex flex-col gap-4">
          <div>
            <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-foreground">
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              maxLength={254}
              disabled={pending}
              placeholder="you@example.com"
              className={inputClass}
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-foreground">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              required
              minLength={8}
              disabled={pending}
              placeholder="At least 8 characters"
              className={inputClass}
            />
          </div>

          {shownError && (
            <p
              className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm text-destructive"
              role="alert"
            >
              {shownError}
            </p>
          )}
          {state.notice && (
            <p
              className="rounded-xl border border-accent/30 bg-accent/10 px-4 py-2.5 text-sm text-foreground"
              role="status"
            >
              {state.notice}
            </p>
          )}

          <GoldButton type="submit" disabled={pending} className="w-full">
            {pending ? (
              <TypingDots label={mode === "signup" ? "Creating your account" : "Signing you in"} />
            ) : mode === "signup" ? (
              "Create account"
            ) : (
              "Sign in"
            )}
          </GoldButton>
        </form>

        <div className="my-6 flex items-center gap-3" aria-hidden>
          <span className="h-px flex-1 bg-border" />
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            or
          </span>
          <span className="h-px flex-1 bg-border" />
        </div>

        <form action={linkAction} className="flex flex-col gap-3">
          <label htmlFor="magic-email" className="text-sm font-medium text-foreground">
            Passwordless sign-in
          </label>
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              id="magic-email"
              name="email"
              type="email"
              autoComplete="email"
              required
              maxLength={254}
              disabled={linkPending}
              placeholder="you@example.com"
              className={`${inputClass} flex-1`}
            />
            <button
              type="submit"
              disabled={linkPending}
              className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-medium text-foreground transition-colors duration-200 hover:border-accent/60 hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Mail className="h-4 w-4" aria-hidden />
              {linkPending ? "Sending…" : "Email me a link"}
            </button>
          </div>
          {linkState.error && (
            <p className="text-sm text-destructive" role="alert">
              {linkState.error}
            </p>
          )}
          {linkState.notice && (
            <p className="text-sm text-foreground" role="status">
              {linkState.notice}
            </p>
          )}
        </form>
      </div>

      <p className="mt-6 text-center text-xs text-muted-foreground">
        All money is paper money. Not financial advice.
      </p>
    </div>
  );
}
