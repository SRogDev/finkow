/**
 * Typed client for the Finkow FastAPI backend.
 *
 * Money is always a decimal STRING in the API contract. This module passes
 * those strings through untouched — formatting for display lives in
 * `lib/format.ts`, and all arithmetic happens server-side.
 */

/**
 * Resolve the backend base URL. `NEXT_PUBLIC_FINKOW_API_URL` is the
 * canonical name (also used by the HTTP adapter in `finkow-client.ts`);
 * `NEXT_PUBLIC_API_URL` is accepted as a legacy alias.
 *
 * NOTE: the `process.env.NEXT_PUBLIC_*` member expressions MUST stay
 * direct — Next.js inlines them textually at build time. Do not route
 * them through an env-object parameter (DefinePlugin won't replace
 * `env.NEXT_PUBLIC_*`, and the browser would silently fall back to the
 * default).
 */
export function resolveApiBase(
  finkowUrl?: string,
  legacyUrl?: string,
): string {
  return finkowUrl ?? legacyUrl ?? "http://localhost:8000";
}

const API_BASE = resolveApiBase(
  process.env.NEXT_PUBLIC_FINKOW_API_URL,
  process.env.NEXT_PUBLIC_API_URL,
);

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Pure header merge, exported for tests: JSON content type always, Bearer
 * token only when a session exists. Never invents a token.
 */
export function mergeAuthHeaders(init: RequestInit | undefined, token: string | null): HeadersInit {
  const headers: Record<string, string> = { "content-type": "application/json" };
  const incoming = init?.headers;
  if (incoming) {
    for (const [key, value] of new Headers(incoming).entries()) {
      headers[key] = value;
    }
  }
  if (token && !headers.authorization) {
    headers.authorization = `Bearer ${token}`;
  }
  return headers;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // The Supabase session token rides along when one exists; when the API
  // runs in dev-mode (no Supabase configured) there is simply no token and
  // no Authorization header is sent.
  const { getAccessToken } = await import("./auth/token.ts");
  const token = await getAccessToken();
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: mergeAuthHeaders(init, token),
    });
  } catch {
    throw new ApiError(0, "The Finkow API is unreachable. Is the backend running?");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      // keep the fallback message
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

/* ------------------------------------------------------------------ */
/* Types (mirroring the FastAPI contract)                              */
/* ------------------------------------------------------------------ */

export interface Account {
  account_id: string;
  /** "experimental" | "real" — the backend's mode separation. */
  mode: string;
  /** True for experimental mode: virtual capital, never real money. */
  virtual: boolean;
  cash: string;
  initial_cash: string;
  created_at: string;
}

export interface Quote {
  symbol: string;
  price: string;
  currency: string;
  as_of: string;
  /** Keyless provider that served this quote (e.g. "stooq", "coingecko", "yahoo"). */
  provider: string;
  stale: boolean;
}

export interface OrderResult {
  transaction_id: string;
  order_id: string;
  mode: string;
  virtual: boolean;
  side: "buy" | "sell";
  symbol: string;
  quantity: string;
  status: string;
  price: string;
  cash_after: string;
  realized_pnl: string | null;
  stale_price: boolean;
  reject_reason: string | null;
}

export interface Position {
  symbol: string;
  quantity: string;
  avg_cost: string;
  price: string;
  market_value: string;
  unrealized_pnl: string;
  unrealized_pnl_pct: string;
  stale: boolean;
}

export interface Portfolio {
  account_id: string;
  /** "experimental" | "real". */
  mode: string;
  /** True for experimental mode: virtual capital, never real money. */
  virtual: boolean;
  cash: string;
  initial_cash: string;
  total_value: string;
  total_return: string;
  total_return_pct: string;
  allocation: Record<string, string>;
  as_of: string;
  positions: Position[];
}

export interface Order {
  order_id: string;
  account_id: string;
  mode: string;
  virtual: boolean;
  symbol: string;
  side: "buy" | "sell";
  quantity: string;
  /** draft | awaiting_authorization | submitted | partially_filled | filled | rejected | cancelled | failed */
  status: string;
  filled_qty: string;
  avg_fill_price: string | null;
  provider_order_id: string | null;
  simulated: boolean;
  reject_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface Transaction {
  id: string;
  mode: string;
  virtual: boolean;
  symbol: string;
  side: "buy" | "sell";
  quantity: string;
  price: string;
  cash_delta: string;
  realized_pnl: string | null;
  order_id: string | null;
  /** proposed | submitted | partially filled | filled | rejected | cancelled | failed */
  status: string;
  simulated: boolean;
  created_at: string;
}

export interface ActivityEvent {
  id: string;
  agent: string;
  kind: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface AuditEntry {
  id: string;
  actor: string;
  action: string;
  account_id: string | null;
  outcome: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface Snapshot {
  total_value: string;
  cash: string;
  created_at: string;
}

export interface ExplainResult {
  answer: string;
  grounded: boolean;
  model: string;
}

/* ------------------------------------------------------------------ */
/* Endpoints                                                           */
/* ------------------------------------------------------------------ */

export async function createAccount(): Promise<Account> {
  return request<Account>("/api/accounts", { method: "POST", body: "{}" });
}

export async function getQuote(symbol: string): Promise<Quote> {
  return request<Quote>(`/api/quotes/${encodeURIComponent(symbol)}`);
}

export async function placeOrder(input: {
  account_id: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: string;
}): Promise<OrderResult> {
  return request<OrderResult>("/api/orders", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getPortfolio(accountId: string): Promise<Portfolio> {
  return request<Portfolio>(`/api/accounts/${accountId}/portfolio`);
}

export async function getTransactions(accountId: string): Promise<Transaction[]> {
  const body = await request<{ transactions: Transaction[] }>(
    `/api/accounts/${accountId}/transactions`,
  );
  return body.transactions;
}

export async function getHistory(accountId: string): Promise<Snapshot[]> {
  const body = await request<{ snapshots: Snapshot[] }>(`/api/accounts/${accountId}/history`);
  return body.snapshots;
}

export async function getOrders(accountId: string): Promise<Order[]> {
  const body = await request<{ orders: Order[] }>(`/api/accounts/${accountId}/orders`);
  return body.orders;
}

export async function getOrder(orderId: string): Promise<Order> {
  return request<Order>(`/api/orders/${encodeURIComponent(orderId)}`);
}

export async function getActivity(): Promise<ActivityEvent[]> {
  const body = await request<{ events: ActivityEvent[] }>("/api/agents/activity");
  return body.events;
}

export async function getAudit(accountId?: string): Promise<AuditEntry[]> {
  const path =
    accountId != null ? `/api/audit?account_id=${encodeURIComponent(accountId)}` : "/api/audit";
  const body = await request<{ entries: AuditEntry[] }>(path);
  return body.entries;
}

export async function explainPortfolio(input: {
  account_id: string;
  question: string;
}): Promise<ExplainResult> {
  return request<ExplainResult>("/api/ai/explain", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

/* ------------------------------------------------------------------ */
/* Account bootstrap — one sandbox account per browser, persisted in    */
/* localStorage and reused on later visits.                            */
/* ------------------------------------------------------------------ */

const ACCOUNT_KEY = "finkow_account_id";

export function getStoredAccountId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCOUNT_KEY);
}

export async function getOrCreateAccountId(): Promise<string> {
  const stored = getStoredAccountId();
  if (stored) return stored;
  const account = await createAccount();
  window.localStorage.setItem(ACCOUNT_KEY, account.account_id);
  return account.account_id;
}
