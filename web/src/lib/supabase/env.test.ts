import assert from "node:assert/strict";
import { test } from "node:test";
import { isSupabaseConfigured, supabaseEnv } from "./env.ts";

const URL = "https://xyzcompany.supabase.co";
const KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test";

function withEnv(vars: Record<string, string | undefined>, fn: () => void) {
  const prev = { ...process.env };
  for (const [k, v] of Object.entries(vars)) {
    if (v === undefined) delete process.env[k];
    else process.env[k] = v;
  }
  try {
    fn();
  } finally {
    process.env = prev;
  }
}

test("isSupabaseConfigured is true when both vars are set", () => {
  withEnv({ NEXT_PUBLIC_SUPABASE_URL: URL, NEXT_PUBLIC_SUPABASE_ANON_KEY: KEY }, () => {
    assert.equal(isSupabaseConfigured(), true);
  });
});

test("isSupabaseConfigured is false when url is missing", () => {
  withEnv({ NEXT_PUBLIC_SUPABASE_URL: undefined, NEXT_PUBLIC_SUPABASE_ANON_KEY: KEY }, () => {
    assert.equal(isSupabaseConfigured(), false);
  });
});

test("isSupabaseConfigured is false when anon key is missing", () => {
  withEnv({ NEXT_PUBLIC_SUPABASE_URL: URL, NEXT_PUBLIC_SUPABASE_ANON_KEY: undefined }, () => {
    assert.equal(isSupabaseConfigured(), false);
  });
});

test("isSupabaseConfigured is false when both are missing", () => {
  withEnv({ NEXT_PUBLIC_SUPABASE_URL: undefined, NEXT_PUBLIC_SUPABASE_ANON_KEY: undefined }, () => {
    assert.equal(isSupabaseConfigured(), false);
  });
});

test("isSupabaseConfigured ignores blank strings", () => {
  withEnv({ NEXT_PUBLIC_SUPABASE_URL: "  ", NEXT_PUBLIC_SUPABASE_ANON_KEY: "" }, () => {
    assert.equal(isSupabaseConfigured(), false);
  });
});

test("supabaseEnv returns trimmed values", () => {
  withEnv({ NEXT_PUBLIC_SUPABASE_URL: ` ${URL} `, NEXT_PUBLIC_SUPABASE_ANON_KEY: KEY }, () => {
    assert.deepEqual(supabaseEnv(), { url: URL, anonKey: KEY });
  });
});

test("supabaseEnv returns nulls when unconfigured", () => {
  withEnv({ NEXT_PUBLIC_SUPABASE_URL: undefined, NEXT_PUBLIC_SUPABASE_ANON_KEY: undefined }, () => {
    assert.deepEqual(supabaseEnv(), { url: null, anonKey: null });
  });
});
