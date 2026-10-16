"use client";

import { ArrowDownRight, ArrowLeft, ArrowUpRight, BadgeDollarSign, History } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Card,
  CardTitle,
  ErrorState,
  Field,
  inputClassName,
  LoadingState,
  PrimaryButton,
  SignedMoney,
  StaleBadge,
} from "@/components/ui";
import {
  ApiError,
  getOrCreateAccountId,
  getPortfolio,
  getQuote,
  getTransactions,
  type OrderResult,
  type Position,
  placeOrder,
  type Quote,
  type Transaction,
} from "@/lib/api";
import { formatDateTime, formatMoney, formatQuantity } from "@/lib/format";
import { validateQuantity } from "@/lib/order";

/* ------------------------------------------------------------------ */

export function AssetInspectorClient({ symbol }: { symbol: string }) {
  const upper = symbol.toUpperCase();
  const [accountId, setAccountId] = useState<string | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [position, setPosition] = useState<Position | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const id = await getOrCreateAccountId();
      setAccountId(id);
      const [q, portfolio, txs] = await Promise.all([
        getQuote(upper),
        getPortfolio(id),
        getTransactions(id),
      ]);
      setQuote(q);
      setPosition(portfolio.positions.find((p) => p.symbol === upper) ?? null);
      setTransactions(txs.filter((t) => t.symbol.toUpperCase() === upper).slice(0, 10));
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : `Could not load data for ${upper}.`);
    } finally {
      setLoading(false);
    }
  }, [upper]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingState label={`Loading ${upper}…`} />;
  if (error || !accountId) {
    return (
      <ErrorState
        message={error ?? "Could not load asset data."}
        onRetry={() => {
          setLoading(true);
          load();
        }}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <Link
        href="/"
        className="inline-flex w-fit cursor-pointer items-center gap-1.5 text-sm text-muted-foreground transition-colors duration-200 hover:text-accent"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden />
        Back to dashboard
      </Link>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="flex flex-col gap-6 lg:col-span-3">
          {quote ? (
            <QuoteCard quote={quote} />
          ) : (
            <ErrorState message={`No quote available for ${upper}.`} />
          )}
          {position && <PositionCard position={position} />}
          <TransactionsCard transactions={transactions} symbol={upper} />
        </div>
        <div className="lg:col-span-2">
          {quote && (
            <OrderForm symbol={upper} accountId={accountId} quote={quote} onFilled={load} />
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function QuoteCard({ quote }: { quote: Quote }) {
  return (
    <Card>
      <CardTitle
        action={
          <span className="flex items-center gap-2">
            {quote.stale && <StaleBadge />}
            <span className="rounded-full border border-border bg-muted px-2.5 py-0.5 text-xs text-muted-foreground">
              {quote.provider}
            </span>
          </span>
        }
      >
        {quote.symbol}
      </CardTitle>
      <p className="tnum text-5xl font-bold text-accent">{formatMoney(quote.price)}</p>
      <p className="mt-2 text-xs text-muted-foreground">
        {quote.currency} · as of {formatDateTime(quote.as_of)}
      </p>
    </Card>
  );
}

/* ------------------------------------------------------------------ */

function PositionCard({ position }: { position: Position }) {
  return (
    <Card>
      <CardTitle action={position.stale ? <StaleBadge /> : undefined}>Your position</CardTitle>
      <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-muted-foreground">Quantity</dt>
          <dd className="tnum mt-1 font-semibold">{formatQuantity(position.quantity)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Avg cost</dt>
          <dd className="tnum mt-1 font-semibold">{formatMoney(position.avg_cost)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Market value</dt>
          <dd className="tnum mt-1 font-semibold">{formatMoney(position.market_value)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Unrealized P&L</dt>
          <dd className="tnum mt-1">
            <SignedMoney value={position.unrealized_pnl} />
          </dd>
        </div>
      </dl>
    </Card>
  );
}

/* ------------------------------------------------------------------ */

function TransactionsCard({
  transactions,
  symbol,
}: {
  transactions: Transaction[];
  symbol: string;
}) {
  return (
    <Card>
      <CardTitle>
        <span className="inline-flex items-center gap-2">
          <History className="h-4 w-4" aria-hidden />
          Recent {symbol} trades
        </span>
      </CardTitle>
      {transactions.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No trades in {symbol} yet — your first order will appear here.
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-border/50">
          {transactions.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-3 py-3 text-sm">
              <span className="flex items-center gap-2">
                {t.side === "buy" ? (
                  <ArrowUpRight className="h-4 w-4 text-success" aria-label="Buy" />
                ) : (
                  <ArrowDownRight className="h-4 w-4 text-destructive" aria-label="Sell" />
                )}
                <span className="font-medium capitalize">{t.side}</span>
                <span className="tnum text-muted-foreground">
                  {formatQuantity(t.quantity)} @ {formatMoney(t.price)}
                </span>
              </span>
              <span className="text-right">
                <span className="tnum block font-medium">
                  <SignedMoney value={t.cash_delta} />
                </span>
                <span className="block text-xs text-muted-foreground">
                  {formatDateTime(t.created_at)}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ */

function OrderForm({
  symbol,
  accountId,
  quote,
  onFilled,
}: {
  symbol: string;
  accountId: string;
  quote: Quote;
  onFilled: () => void;
}) {
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [quantityInput, setQuantityInput] = useState("1");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [result, setResult] = useState<OrderResult | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  const estimate = useMemo(() => {
    const v = validateQuantity(quantityInput);
    if (!v.ok) return null;
    const price = Number(quote.price);
    if (!Number.isFinite(price)) return null;
    // Display-only estimate: quantity × price. The real fill price comes
    // from the backend at order time.
    return price * Number(v.quantity);
  }, [quantityInput, quote.price]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setApiError(null);
    setResult(null);
    const v = validateQuantity(quantityInput);
    if (!v.ok) {
      setFormError(v.error);
      return;
    }
    setSubmitting(true);
    try {
      const res = await placeOrder({
        account_id: accountId,
        symbol,
        side,
        quantity: v.quantity,
      });
      setResult(res);
      onFilled();
    } catch (e2) {
      setApiError(e2 instanceof ApiError ? e2.detail : "The order could not be placed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="lg:sticky lg:top-6">
      <CardTitle>
        <span className="inline-flex items-center gap-2">
          <BadgeDollarSign className="h-4 w-4 text-accent" aria-hidden />
          Trade {symbol}
        </span>
      </CardTitle>

      <form onSubmit={submit} className="flex flex-col gap-4">
        <fieldset className="grid grid-cols-2 gap-1 rounded-lg border border-border bg-background p-1">
          <legend className="sr-only">Order side</legend>
          {(["buy", "sell"] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSide(s)}
              aria-pressed={side === s}
              className={`cursor-pointer rounded-md px-4 py-2 text-sm font-semibold capitalize transition-all duration-200 ${
                side === s
                  ? s === "buy"
                    ? "bg-success text-background"
                    : "bg-destructive text-background"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {s}
            </button>
          ))}
        </fieldset>

        <Field label="Quantity" hint="Fractional quantities allowed (up to 8 decimals).">
          <input
            value={quantityInput}
            onChange={(e) => setQuantityInput(e.target.value)}
            inputMode="decimal"
            placeholder="1"
            aria-label="Quantity"
            className={inputClassName}
          />
        </Field>

        <div className="rounded-lg border border-border bg-background p-3 text-sm">
          <div className="flex items-center justify-between text-muted-foreground">
            <span>Estimated {side === "buy" ? "cost" : "proceeds"}</span>
            <span className="tnum font-semibold text-foreground">
              {estimate === null
                ? "—"
                : new Intl.NumberFormat("en-US", {
                    style: "currency",
                    currency: "USD",
                  }).format(estimate)}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Based on the latest quote — the fill price is confirmed at order time.
          </p>
        </div>

        {formError && (
          <p className="text-sm text-destructive" role="alert">
            {formError}
          </p>
        )}
        {apiError && (
          <p className="text-sm text-destructive" role="alert">
            {apiError}
          </p>
        )}

        <PrimaryButton type="submit" disabled={submitting}>
          {submitting ? "Placing order…" : `${side === "buy" ? "Buy" : "Sell"} ${symbol}`}
        </PrimaryButton>
      </form>

      {result && (
        <div
          className="mt-4 rounded-lg border border-success/40 bg-success/5 p-4 text-sm"
          role="status"
        >
          <p className="font-semibold text-success">
            Order filled — {result.side} {formatQuantity(result.quantity)} {result.symbol}
          </p>
          <dl className="mt-2 grid grid-cols-2 gap-2 text-muted-foreground">
            <div>
              <dt>Fill price</dt>
              <dd className="tnum font-medium text-foreground">{formatMoney(result.price)}</dd>
            </div>
            <div>
              <dt>Cash after</dt>
              <dd className="tnum font-medium text-foreground">{formatMoney(result.cash_after)}</dd>
            </div>
          </dl>
          {result.realized_pnl !== null && (
            <p className="mt-2">
              Realized P&L: <SignedMoney value={result.realized_pnl} />
            </p>
          )}
          {result.stale_price && (
            <p className="mt-2">
              <StaleBadge />
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
