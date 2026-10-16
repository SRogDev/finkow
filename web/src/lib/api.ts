/**
 * Typed client for the Finkow FastAPI backend.
 *
 * Money is always a decimal STRING in the API contract. This module passes
 * those strings through untouched — formatting for display lives in
 * `lib/format.ts`, and all arithmetic happens server-side.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...init?.headers },
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
  side: "buy" | "sell";
  symbol: string;
  quantity: string;
  price: string;
  cash_after: string;
  realized_pnl: string | null;
  stale_price: boolean;
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
  cash: string;
  initial_cash: string;
  total_value: string;
  total_return: string;
  total_return_pct: string;
  allocation: Record<string, string>;
  as_of: string;
  positions: Position[];
}

export interface Transaction {
  id: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: string;
  price: string;
  cash_delta: string;
  realized_pnl: string | null;
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
