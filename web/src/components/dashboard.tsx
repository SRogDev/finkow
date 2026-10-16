"use client";

import {
  ArrowRight,
  Landmark,
  RefreshCw,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Card,
  CardTitle,
  ErrorState,
  GroundedBadge,
  LoadingState,
  PrimaryButton,
  SignedMoney,
  SignedPercent,
} from "@/components/ui";
import {
  ApiError,
  explainPortfolio,
  getOrCreateAccountId,
  getPortfolio,
  getTransactions,
  type Portfolio,
  type Transaction,
} from "@/lib/api";
import { formatDateTime, formatMoney, formatPercent, formatQuantity } from "@/lib/format";

/* ------------------------------------------------------------------ */
/* Portfolio view: total value → performance → gains/losses →          */
/* allocation → positions → recent transactions → full history.         */
/* ------------------------------------------------------------------ */

export function DashboardClient() {
  const [accountId, setAccountId] = useState<string | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const id = await getOrCreateAccountId();
      setAccountId(id);
      // Independent reads — one slow source must not block the others.
      const [data, txs] = await Promise.all([getPortfolio(id), getTransactions(id)]);
      setPortfolio(data);
      setTransactions(txs);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.detail : "Something went wrong while loading your portfolio.",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingState label="Opening your portfolio…" />;
  if (error || !portfolio || !accountId) {
    return (
      <ErrorState
        message={error ?? "Could not load your portfolio."}
        onRetry={() => {
          setLoading(true);
          load();
        }}
      />
    );
  }

  const refresh = () => {
    setRefreshing(true);
    load();
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="mb-2 flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-accent">
          Portfolio
          {portfolio.virtual ? (
            <span className="rounded-full border border-accent/40 bg-accent/10 px-2.5 py-0.5 text-[10px] font-semibold normal-case tracking-normal text-accent">
              Experimental · virtual capital
            </span>
          ) : (
            <span className="rounded-full border border-border px-2.5 py-0.5 text-[10px] font-semibold normal-case tracking-normal text-muted-foreground">
              Real mode
            </span>
          )}
        </p>
        <h1 className="font-display text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
          Your money, at a glance
        </h1>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">
          {portfolio.virtual
            ? "Virtual capital in an experimental sandbox — practice without risk. Never real money."
            : "Real-money mode. No execution path is connected in this build."}
        </p>
      </div>

      <StatsRow portfolio={portfolio} />

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <AllocationCard portfolio={portfolio} />
        </div>
        <div className="lg:col-span-3">
          <PositionsCard portfolio={portfolio} />
        </div>
      </div>

      <TransactionsCard transactions={transactions} />

      <ExplainPanel accountId={accountId} />

      <p className="text-center text-xs text-muted-foreground">
        Last valued {formatDateTime(portfolio.as_of)} ·{" "}
        <button
          type="button"
          onClick={refresh}
          className="inline-flex cursor-pointer items-center gap-1 text-accent underline-offset-2 transition-opacity duration-200 hover:opacity-80 hover:underline"
        >
          <RefreshCw className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`} aria-hidden />
          Refresh
        </button>
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function StatsRow({ portfolio }: { portfolio: Portfolio }) {
  const returnPositive = Number(portfolio.total_return) >= 0;
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <Card className="border-accent/30">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Landmark className="h-4 w-4" aria-hidden />
          Total value
        </div>
        <p className="tnum mt-2 text-4xl font-bold text-accent">
          {formatMoney(portfolio.total_value)}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {portfolio.virtual ? "Virtual · USD" : "USD"}
        </p>
      </Card>

      <Card>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          {returnPositive ? (
            <TrendingUp className="h-4 w-4" aria-hidden />
          ) : (
            <TrendingDown className="h-4 w-4" aria-hidden />
          )}
          Total return
        </div>
        <p className="tnum mt-2 text-4xl font-bold">
          <SignedMoney value={portfolio.total_return} />
        </p>
        <p className="mt-1 text-sm">
          <SignedPercent value={portfolio.total_return_pct} /> all time
        </p>
      </Card>

      <Card>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Wallet className="h-4 w-4" aria-hidden />
          Cash available
        </div>
        <p className="tnum mt-2 text-4xl font-bold">{formatMoney(portfolio.cash)}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          of {formatMoney(portfolio.initial_cash)} starting cash
        </p>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function AllocationCard({ portfolio }: { portfolio: Portfolio }) {
  const entries = Object.entries(portfolio.allocation)
    .map(([symbol, weight]) => ({ symbol, weight: Number(weight) }))
    .filter((e) => Number.isFinite(e.weight) && e.weight > 0)
    .sort((a, b) => b.weight - a.weight);

  return (
    <Card className="h-full">
      <CardTitle>Allocation</CardTitle>
      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No allocation data yet. Buy an asset to see how your portfolio is distributed.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {entries.map(({ symbol, weight }) => (
            <li key={symbol}>
              <div className="mb-1 flex items-center justify-between text-sm">
                <Link
                  href={symbol === "CASH" ? "/portfolio" : `/assets/${symbol}`}
                  className="cursor-pointer font-medium text-foreground transition-colors duration-200 hover:text-accent"
                >
                  {symbol}
                </Link>
                <span className="tnum text-muted-foreground">
                  {formatPercent(String(weight * 100))}
                </span>
              </div>
              <div
                className="h-2 overflow-hidden rounded-full bg-muted"
                role="img"
                aria-label={`${symbol}: ${formatPercent(String(weight * 100))}`}
              >
                <div
                  className={`h-full rounded-full transition-all duration-300 ${
                    symbol === "CASH" ? "bg-muted-foreground" : "bg-accent"
                  }`}
                  style={{ width: `${Math.min(100, weight * 100)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ */

function PositionsCard({ portfolio }: { portfolio: Portfolio }) {
  if (portfolio.positions.length === 0) {
    return (
      <Card className="h-full">
        <CardTitle>Positions</CardTitle>
        <div className="flex flex-col items-start gap-3">
          <p className="text-sm text-muted-foreground">
            You don&apos;t hold anything yet. Your {formatMoney(portfolio.cash)} is sitting in cash
            — pick an asset and make your first virtual trade.
          </p>
          <Link
            href="/assets/AAPL"
            className="inline-flex cursor-pointer items-center gap-1.5 text-sm font-medium text-accent transition-opacity duration-200 hover:opacity-80"
          >
            Inspect AAPL <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        </div>
      </Card>
    );
  }

  return (
    <Card className="h-full overflow-hidden">
      <CardTitle>Positions</CardTitle>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
              <th className="pb-2 pr-4 font-medium">Symbol</th>
              <th className="pb-2 pr-4 text-right font-medium">Qty</th>
              <th className="pb-2 pr-4 text-right font-medium">Avg cost</th>
              <th className="pb-2 pr-4 text-right font-medium">Price</th>
              <th className="pb-2 pr-4 text-right font-medium">Value</th>
              <th className="pb-2 text-right font-medium">Unrealized P&L</th>
            </tr>
          </thead>
          <tbody>
            {portfolio.positions.map((p) => (
              <tr
                key={p.symbol}
                className="border-b border-border/50 transition-colors duration-200 last:border-0 hover:bg-muted/40"
              >
                <td className="py-3 pr-4">
                  <Link
                    href={`/assets/${p.symbol}`}
                    className="cursor-pointer font-semibold text-accent transition-opacity duration-200 hover:opacity-80"
                  >
                    {p.symbol}
                  </Link>
                </td>
                <td className="tnum py-3 pr-4 text-right">{formatQuantity(p.quantity)}</td>
                <td className="tnum py-3 pr-4 text-right text-muted-foreground">
                  {formatMoney(p.avg_cost)}
                </td>
                <td className="tnum py-3 pr-4 text-right">{formatMoney(p.price)}</td>
                <td className="tnum py-3 pr-4 text-right font-medium">
                  {formatMoney(p.market_value)}
                </td>
                <td className="tnum py-3 text-right">
                  <SignedMoney value={p.unrealized_pnl} />
                  <span className="text-xs">
                    {" "}
                    (<SignedPercent value={p.unrealized_pnl_pct} />)
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ */

const PAGE_SIZE = 10;

function statusTone(status: string): string {
  const s = status.toLowerCase();
  if (s === "filled") return "text-success";
  if (s === "rejected" || s === "failed" || s === "cancelled") return "text-destructive";
  return "text-accent";
}

function TransactionsCard({ transactions }: { transactions: Transaction[] }) {
  const [visible, setVisible] = useState(PAGE_SIZE);

  return (
    <Card>
      <CardTitle
        action={
          <span className="text-xs font-medium text-muted-foreground">
            {transactions.length} total
          </span>
        }
      >
        Transaction history
      </CardTitle>
      {transactions.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No transactions yet — your virtual trades will appear here with their full status.
        </p>
      ) : (
        <div>
          <ul className="flex flex-col divide-y divide-border/50">
            {transactions.slice(0, visible).map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold capitalize text-foreground">{t.side}</span>
                    <Link
                      href={`/assets/${t.symbol}`}
                      className="cursor-pointer font-medium text-accent transition-opacity duration-200 hover:opacity-80"
                    >
                      {t.symbol}
                    </Link>
                    <span
                      className={`text-xs font-semibold uppercase tracking-wide ${statusTone(t.status)}`}
                    >
                      {t.status.replace(/_/g, " ")}
                    </span>
                    {t.virtual && (
                      <span className="rounded-full border border-accent/40 bg-accent/10 px-1.5 py-px text-[10px] font-medium text-accent">
                        Virtual
                      </span>
                    )}
                  </p>
                  <p className="tnum mt-0.5 text-xs text-muted-foreground">
                    {formatQuantity(t.quantity)} @ {formatMoney(t.price)} ·{" "}
                    {formatDateTime(t.created_at)}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="tnum font-medium">
                    <SignedMoney value={t.cash_delta} />
                  </p>
                  {t.realized_pnl !== null && (
                    <p className="tnum text-xs text-muted-foreground">
                      P&L <SignedMoney value={t.realized_pnl} />
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {visible < transactions.length && (
            <button
              type="button"
              onClick={() => setVisible((v) => v + PAGE_SIZE)}
              className="mt-3 inline-flex cursor-pointer items-center gap-1.5 text-sm font-medium text-accent transition-opacity duration-200 hover:opacity-80"
            >
              Show more ({transactions.length - visible} remaining)
            </button>
          )}
        </div>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ */

const DEFAULT_QUESTION = "What happened to my portfolio recently?";

function ExplainPanel({ accountId }: { accountId: string }) {
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [answer, setAnswer] = useState<string | null>(null);
  const [grounded, setGrounded] = useState(false);
  const [model, setModel] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = async () => {
    if (!question.trim() || asking) return;
    setAsking(true);
    setError(null);
    try {
      const res = await explainPortfolio({ account_id: accountId, question });
      setAnswer(res.answer);
      setGrounded(res.grounded);
      setModel(res.model);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "The AI explanation is unavailable right now.");
    } finally {
      setAsking(false);
    }
  };

  return (
    <Card>
      <CardTitle action={answer !== null ? <GroundedBadge grounded={grounded} /> : undefined}>
        <span className="inline-flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-accent" aria-hidden />
          Ask about your portfolio
        </span>
      </CardTitle>
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") ask();
          }}
          placeholder={DEFAULT_QUESTION}
          aria-label="Question about your portfolio"
          className="w-full rounded-xl border border-border bg-background px-4 py-2.5 text-base text-foreground placeholder:text-muted-foreground/60 transition-colors duration-200 focus:border-accent"
        />
        <PrimaryButton onClick={ask} disabled={asking} className="shrink-0">
          {asking ? "Thinking…" : "Explain"}
        </PrimaryButton>
      </div>
      {error && (
        <p className="mt-3 text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
      {answer !== null && !error && (
        <div className="mt-4 rounded-xl border border-border bg-background p-4">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{answer}</p>
          {model && <p className="mt-3 text-xs text-muted-foreground">Answered by {model}</p>}
        </div>
      )}
    </Card>
  );
}
