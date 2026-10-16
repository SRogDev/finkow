/**
 * Finkow v2 API client.
 *
 * The UI talks to this client only — never to fetch() directly — so the
 * product works end to end against a deterministic mock or the real FastAPI
 * backend. No invented endpoints: the HTTP adapter maps 1:1 to the
 * backend's /api routes (Phase 4: mode/virtual flags, order lifecycle,
 * activity/audit). The mock adapter mirrors the same interface with
 * deterministic demo data.
 *
 * Adapter selection: mock is the default (fully demonstrable, no backend).
 * Set NEXT_PUBLIC_FINKOW_ADAPTER=http with NEXT_PUBLIC_FINKOW_API_URL to
 * talk to the real API. When Supabase is configured, the session's Bearer
 * token rides along automatically; without it, the API runs in dev-mode.
 */

import { getAccessToken } from "./auth/token.ts";

export type RiskLevel = "low" | "medium" | "high";
export type AgentName = "Radar" | "Pilot" | "Planner" | "Explainer";

export interface Goal {
  id: string;
  text: string;
  createdAt: string;
  /** Backend account bound to this goal (real account id, or "mock-account"). */
  accountId: string;
}

export interface AllocationSlice {
  label: string;
  percent: number;
  why: string;
}

export interface Plan {
  id: string;
  goalId: string;
  headline: string;
  summary: string;
  horizon: string;
  risk: RiskLevel;
  allocations: AllocationSlice[];
  monthlyNote: string;
}

export interface Opportunity {
  id: string;
  title: string;
  category: string;
  summary: string;
  why: string[];
  riskNote: string;
  minAmountUsd: number;
  /** Supporting evidence, in plain language. Absent when the agents have none yet. */
  evidence?: string[];
  /** The action Finkow proposes, if any. Always virtual (paper) money. */
  proposal?: { amountUsd: number; rationale: string };
}

export interface Position {
  id: string;
  label: string;
  valueUsd: number;
  dayChangePct: number;
  note: string;
}

export interface Portfolio {
  totalValueUsd: number;
  dayChangeUsd: number;
  dayChangePct: number;
  /** What the change number measures: "today" (mock) or "all time" (real API). */
  changeLabel?: string;
  pulseText: string;
  pulseDetail: string;
  positions: Position[];
  /** True when the money is virtual (experimental mode). */
  virtual?: boolean;
  mode?: string;
  asOf?: string;
}

export interface AgentEvent {
  id: string;
  agent: AgentName;
  text: string;
  at: string;
}

export interface ExplanationFact {
  label: string;
  detail: string;
}

export interface Explanation {
  answer: string;
  facts: ExplanationFact[];
}

export interface InvestResult {
  positionId: string;
  message: string;
}

export interface FinkowClient {
  /** POST /goals */
  createGoal(text: string): Promise<Goal>;
  /** GET /goals/{id}/plan */
  getPlan(goalId: string): Promise<Plan>;
  /** GET /radar/opportunities */
  getOpportunities(): Promise<Opportunity[]>;
  /** POST /portfolio/invest (paper money only) */
  invest(opportunityId: string, amountUsd: number): Promise<InvestResult>;
  /** GET /portfolio */
  getPortfolio(): Promise<Portfolio>;
  /** POST /explain */
  explain(question: string): Promise<Explanation>;
  /** GET /agents/activity */
  getActivity(): Promise<AgentEvent[]>;
}

/* ------------------------------------------------------------------ */
/* Mock adapter: deterministic demo data, in-memory paper portfolio.    */
/* ------------------------------------------------------------------ */

const MOCK_PORTFOLIO: Portfolio = {
  totalValueUsd: 1128.4,
  dayChangeUsd: 12.4,
  dayChangePct: 1.1,
  changeLabel: "today",
  virtual: true,
  mode: "experimental",
  pulseText: "Your money is working.",
  pulseDetail:
    "Up $12.40 today — mostly from clean energy and steady earners. Nothing needs your attention right now.",
  positions: [
    {
      id: "pos-steady",
      label: "Steady earners",
      valueUsd: 640.1,
      dayChangePct: 0.4,
      note: "Large, profitable companies that grow slowly and pay you along the way.",
    },
    {
      id: "pos-clean",
      label: "Clean energy",
      valueUsd: 312.55,
      dayChangePct: 2.8,
      note: "Companies building solar, wind, and batteries for the next decades.",
    },
    {
      id: "pos-cash",
      label: "Cash, ready to move",
      valueUsd: 175.75,
      dayChangePct: 0,
      note: "Waiting for the next opportunity your agents find.",
    },
  ],
};

const MOCK_OPPORTUNITIES: Opportunity[] = [
  {
    id: "opp-clean-energy",
    title: "Clean energy momentum",
    category: "Growth",
    summary:
      "Falling costs and new projects keep pushing clean energy higher. Your agents see steady buying over the last two weeks.",
    why: [
      "New solar and battery projects were announced in three countries this month.",
      "Buying has been steady for two weeks, not a one-day spike.",
      "Fits your low-risk goal: a years-long trend, not a gamble.",
    ],
    riskNote: "Prices can swing day to day. Think years, not weeks.",
    evidence: [
      "Your agents logged steady buying over the last two weeks — visible in your activity feed.",
      "New solar and battery projects were announced in three countries this month.",
    ],
    proposal: {
      amountUsd: 100,
      rationale: "A small virtual slice of a years-long trend, sized to stay calm.",
    },
    minAmountUsd: 25,
  },
  {
    id: "opp-everyday-tech",
    title: "Everyday tech giants",
    category: "Steady",
    summary:
      "The world's largest technology companies keep growing their profits. Boring, reliable, and compounding.",
    why: [
      "Profits grew again last quarter across the group.",
      "They return cash to owners through dividends and buybacks.",
      "Low drama: the calm core of most long-term plans.",
    ],
    riskNote: "Slow and steady — don't expect fireworks.",
    evidence: [
      "Group profits grew again last quarter — your agents track the filings.",
      "These companies return cash to owners through dividends and buybacks.",
    ],
    proposal: {
      amountUsd: 100,
      rationale: "A steady core holding for the calm part of your plan.",
    },
    minAmountUsd: 25,
  },
  {
    id: "opp-healthcare",
    title: "Global healthcare",
    category: "Steady",
    summary:
      "Aging populations need more care. Healthcare companies grow steadily and share profits with owners.",
    why: [
      "Demand grows as populations age — it doesn't depend on fads.",
      "Steady dividends cushion the rough days.",
      "Diversifies you away from tech and energy.",
    ],
    riskNote: "Regulation can surprise; that's why it's a slice, not the whole pie.",
    evidence: [
      "Dividend payments continued through recent market dips.",
      "Demand for care grows with aging populations — a structural trend, not a fad.",
    ],
    proposal: {
      amountUsd: 100,
      rationale: "A diversifying slice away from tech and energy.",
    },
    minAmountUsd: 25,
  },
  {
    id: "opp-green-metals",
    title: "Metals for the energy transition",
    category: "Growth",
    summary:
      "Batteries and power lines need copper, lithium, and nickel. Demand is outgrowing supply.",
    why: [
      "Every electric car and solar farm needs these metals.",
      "Mines take years to open, so supply can't catch up quickly.",
      "A small slice adds punch to a calm portfolio.",
    ],
    riskNote: "The bumpiest ride of the four — keep it small.",
    evidence: [
      "Copper and lithium demand is outgrowing new mine supply.",
      "Mines take years to open, which your agents track in the activity feed.",
    ],
    proposal: {
      amountUsd: 100,
      rationale: "A small, punchier slice — keep it small because prices swing.",
    },
    minAmountUsd: 25,
  },
];

const MOCK_PLAN: Plan = {
  id: "plan-1",
  goalId: "goal-1",
  headline: "A calm 5-year plan for your $1,000",
  summary:
    "You want growth without the rollercoaster. This plan spreads your $1,000 across steady earners and long-term trends, keeps some cash ready, and lets compounding do the heavy lifting. No day-trading, no panic buttons.",
  horizon: "5 years",
  risk: "low",
  allocations: [
    {
      label: "Steady earners",
      percent: 50,
      why: "The calm core. Large profitable companies that grow slowly and share profits with you.",
    },
    {
      label: "Clean energy",
      percent: 25,
      why: "Your growth engine. A decades-long trend with real momentum right now.",
    },
    {
      label: "Global healthcare",
      percent: 15,
      why: "Balance. Demand that doesn't depend on the economy's mood.",
    },
    {
      label: "Cash, ready to move",
      percent: 10,
      why: "Flexibility. Lets your agents pounce when the next opportunity appears.",
    },
  ],
  monthlyNote:
    "Adding even $50 a month could grow this to roughly $1,600 in 5 years at a calm pace. Your agents will remind you — gently.",
};

const MOCK_ACTIVITY: AgentEvent[] = [
  {
    id: "evt-1",
    agent: "Radar",
    text: "Radar found 4 opportunities worth your attention.",
    at: "09:41",
  },
  {
    id: "evt-2",
    agent: "Planner",
    text: "Planner drafted a calm 5-year plan for your $1,000 goal.",
    at: "09:38",
  },
  {
    id: "evt-3",
    agent: "Pilot",
    text: "Pilot checked your portfolio — everything on track, no moves needed.",
    at: "09:15",
  },
  {
    id: "evt-4",
    agent: "Explainer",
    text: "Explainer is ready: ask why anything moved, in plain language.",
    at: "09:00",
  },
];

const MOCK_EXPLANATION: Explanation = {
  answer:
    "Your portfolio is up $12.40 today because clean energy had a strong morning — new project announcements lifted the whole group about 2.8%. Your steady earners added a little too. Nothing dramatic, and nothing you need to do: this is exactly the kind of day your plan was built for.",
  facts: [
    {
      label: "Clean energy",
      detail: "Up 2.8% today on project announcements in three countries.",
    },
    {
      label: "Steady earners",
      detail: "Up 0.4% — a normal, quiet day.",
    },
    {
      label: "Cash reserve",
      detail: "$175.75 waiting for the next opportunity.",
    },
  ],
};

export class MockFinkowClient implements FinkowClient {
  private goalSeq = 1;
  private investSeq = 1;
  private portfolio: Portfolio = structuredClone(MOCK_PORTFOLIO);
  private activity: AgentEvent[] = [...MOCK_ACTIVITY];

  async createGoal(text: string): Promise<Goal> {
    const clean = text.trim();
    if (!clean) throw new Error("Goal text must not be empty.");
    this.goalSeq += 1;
    return {
      id: `goal-${this.goalSeq}`,
      text: clean,
      createdAt: new Date().toISOString(),
      accountId: "mock-account",
    };
  }

  async getPlan(goalId: string): Promise<Plan> {
    if (!goalId) throw new Error("Unknown goal.");
    // Deterministic demo plan; the real backend personalizes it per goal.
    return structuredClone(MOCK_PLAN);
  }

  async getOpportunities(): Promise<Opportunity[]> {
    return structuredClone(MOCK_OPPORTUNITIES);
  }

  async invest(opportunityId: string, amountUsd: number): Promise<InvestResult> {
    const opp = MOCK_OPPORTUNITIES.find((o) => o.id === opportunityId);
    if (!opp) throw new Error(`Unknown opportunity: ${opportunityId}.`);
    if (!Number.isFinite(amountUsd) || amountUsd <= 0) {
      throw new Error("Amount must be a positive number.");
    }
    const existing = this.portfolio.positions.find((p) => p.label === opp.title);
    if (existing) {
      existing.valueUsd = round2(existing.valueUsd + amountUsd);
    } else {
      this.investSeq += 1;
      this.portfolio.positions.push({
        id: `pos-${this.investSeq}`,
        label: opp.title,
        valueUsd: round2(amountUsd),
        dayChangePct: 0,
        note: opp.summary,
      });
    }
    this.portfolio.totalValueUsd = round2(this.portfolio.totalValueUsd + amountUsd);
    this.activity.unshift({
      id: `evt-invest-${this.investSeq}`,
      agent: "Pilot",
      text: `Pilot put $${round2(amountUsd).toFixed(2)} of paper money into ${opp.title}.`,
      at: "now",
    });
    return {
      positionId: existing ? existing.id : `pos-${this.investSeq}`,
      message: `Done — $${round2(amountUsd).toFixed(2)} of paper money is now in ${opp.title}.`,
    };
  }

  async getPortfolio(): Promise<Portfolio> {
    return structuredClone(this.portfolio);
  }

  async explain(question: string): Promise<Explanation> {
    if (!question.trim()) throw new Error("Question must not be empty.");
    return structuredClone(MOCK_EXPLANATION);
  }

  async getActivity(): Promise<AgentEvent[]> {
    return structuredClone(this.activity);
  }
}

/* ------------------------------------------------------------------ */
/* HTTP adapter: talks to the real FastAPI backend (Phase 4 contract). */
/* Every route lives under /api; responses carry mode/virtual flags.   */
/* ------------------------------------------------------------------ */

export interface HttpClientOptions {
  baseUrl?: string;
  /** Sandbox account id; bootstrapped via POST /api/accounts when absent. */
  accountId?: string;
  getToken?: () => Promise<string | null>;
}

interface ApiPosition {
  symbol: string;
  quantity: string;
  avg_cost: string;
  price: string;
  market_value: string;
  unrealized_pnl: string;
  unrealized_pnl_pct: string;
  stale: boolean;
}

interface ApiPortfolio {
  account_id: string;
  mode: string;
  virtual: boolean;
  total_value: string;
  total_return: string;
  total_return_pct: string;
  as_of: string;
  positions: ApiPosition[];
}

export class HttpFinkowClient implements FinkowClient {
  private readonly baseUrl: string;
  private readonly getToken: () => Promise<string | null>;
  private accountId: string | null;
  private goalAccountId: string | null = null;

  constructor(opts: HttpClientOptions = {}) {
    this.baseUrl =
      opts.baseUrl ?? process.env.NEXT_PUBLIC_FINKOW_API_URL ?? "http://localhost:8000";
    this.accountId = opts.accountId ?? null;
    this.getToken = opts.getToken ?? getAccessToken;
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const token = await this.getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: { ...headers, ...(init?.headers ?? {}) },
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(`Finkow API ${res.status} on ${path}${detail ? `: ${detail}` : ""}`);
    }
    return (await res.json()) as T;
  }

  /** Goal account, explicit account, or a freshly bootstrapped sandbox account. */
  private async resolveAccount(): Promise<string> {
    if (this.accountId) return this.accountId;
    if (this.goalAccountId) return this.goalAccountId;
    const account = await this.request<{ account_id: string }>("/api/accounts", {
      method: "POST",
      body: JSON.stringify({}),
    });
    this.accountId = account.account_id;
    return account.account_id;
  }

  async createGoal(text: string): Promise<Goal> {
    const clean = text.trim();
    if (!clean) throw new Error("Goal text must not be empty.");
    const body = await this.request<{
      goal_id: string;
      account_id: string;
      text: string;
      created_at: string;
    }>("/api/goals", { method: "POST", body: JSON.stringify({ text: clean }) });
    this.goalAccountId = body.account_id;
    return {
      id: body.goal_id,
      text: body.text,
      createdAt: body.created_at,
      accountId: body.account_id,
    };
  }

  async getPlan(goalId: string): Promise<Plan> {
    const body = await this.request<{
      goal_id: string;
      summary_plain: string;
      horizon_years: number;
      risk_level: string;
      allocations: { symbol: string; weight: string; rationale: string }[];
    }>(`/api/goals/${encodeURIComponent(goalId)}/plan`);
    const risk: RiskLevel =
      body.risk_level === "low" || body.risk_level === "high" ? body.risk_level : "medium";
    return {
      id: body.goal_id,
      goalId: body.goal_id,
      headline: "Your investment plan",
      summary: body.summary_plain,
      horizon: `${body.horizon_years} ${body.horizon_years === 1 ? "year" : "years"}`,
      risk,
      allocations: body.allocations.map((a) => ({
        label: a.symbol,
        percent: Math.round(Number(a.weight) * 100),
        why: a.rationale || "",
      })),
      monthlyNote: "",
    };
  }

  async getOpportunities(): Promise<Opportunity[]> {
    const body = await this.request<{
      opportunities: { symbol: string; score: number; price: string; reasoning: string }[];
    }>("/api/radar/opportunities");
    return body.opportunities.map((o) => ({
      id: o.symbol,
      title: o.symbol,
      category: "Radar pick",
      summary: o.reasoning,
      why: [o.reasoning],
      riskNote: "Not financial advice. This is virtual money while you learn.",
      minAmountUsd: 0,
    }));
  }

  async invest(opportunityId: string, amountUsd: number): Promise<InvestResult> {
    if (!Number.isFinite(amountUsd) || amountUsd <= 0) {
      throw new Error("Amount must be a positive number.");
    }
    const accountId = await this.resolveAccount();
    const symbol = opportunityId.trim().toUpperCase();
    if (!symbol) throw new Error("Unknown opportunity.");
    const quote = await this.request<{ price: string }>(
      `/api/quotes/${encodeURIComponent(symbol)}`,
    );
    const price = Number(quote.price);
    if (!Number.isFinite(price) || price <= 0) {
      throw new Error(`No usable quote for ${symbol} right now.`);
    }
    // Quantity from a dollar amount; the order API takes decimal quantities.
    const quantity = Number((amountUsd / price).toFixed(8)).toString();
    const order = await this.request<{ order_id: string; status: string; virtual: boolean }>(
      "/api/orders",
      {
        method: "POST",
        body: JSON.stringify({ account_id: accountId, symbol, side: "buy", quantity }),
      },
    );
    const moneyWord = order.virtual ? "virtual money" : "money";
    return {
      positionId: symbol,
      message:
        `Done — $${amountUsd.toFixed(2)} of ${moneyWord} is now in ${symbol} ` +
        `(order ${order.order_id.slice(0, 8)}…, ${humanizeStatus(order.status)}).`,
    };
  }

  async getPortfolio(): Promise<Portfolio> {
    const accountId = await this.resolveAccount();
    const body = await this.request<ApiPortfolio>(`/api/accounts/${accountId}/portfolio`);
    const totalReturn = Number(body.total_return);
    const returnPct = Number(body.total_return_pct);
    return {
      totalValueUsd: Number(body.total_value),
      dayChangeUsd: totalReturn,
      dayChangePct: returnPct,
      changeLabel: "all time",
      pulseText: body.virtual ? "Experimental sandbox." : "Your portfolio.",
      pulseDetail:
        `Valued ${body.as_of}. All-time change ${formatSigned(body.total_return)} ` +
        `(${returnPct.toFixed(2)}%).` +
        (body.virtual ? " Virtual money — not real investing." : ""),
      positions: body.positions.map((p) => ({
        id: p.symbol,
        label: p.symbol,
        valueUsd: Number(p.market_value),
        dayChangePct: Number(p.unrealized_pnl_pct),
        note: `${p.quantity} @ avg ${p.avg_cost}`,
      })),
      virtual: body.virtual,
      mode: body.mode,
      asOf: body.as_of,
    };
  }

  async explain(question: string): Promise<Explanation> {
    const clean = question.trim();
    if (!clean) throw new Error("Question must not be empty.");
    const accountId = await this.resolveAccount();
    const body = await this.request<{ answer: string; grounded: boolean; model: string }>(
      "/api/explain",
      { method: "POST", body: JSON.stringify({ account_id: accountId, question: clean }) },
    );
    // The backend returns a grounded answer without itemized facts; we never
    // invent facts the API did not provide.
    return { answer: body.answer, facts: [] };
  }

  async getActivity(): Promise<AgentEvent[]> {
    const body = await this.request<{
      events: {
        id: string;
        agent: string;
        kind: string;
        payload: Record<string, unknown>;
        created_at: string;
      }[];
    }>("/api/agents/activity");
    return body.events.map((e) => ({
      id: e.id,
      agent: toAgentName(e.agent),
      text: `${humanizeStatus(e.kind)}${payloadNote(e.payload)}`,
      at: e.created_at,
    }));
  }
}

function humanizeStatus(value: string): string {
  const words = value.replace(/[_-]+/g, " ").replace(/\./g, " · ").trim();
  return words.length === 0 ? words : words[0].toUpperCase() + words.slice(1);
}

function payloadNote(payload: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(payload ?? {})) {
    if (parts.length >= 2) break;
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      parts.push(`${key}: ${value}`);
    }
  }
  return parts.length > 0 ? ` — ${parts.join(", ")}` : "";
}

function toAgentName(raw: string): AgentName {
  const lower = raw.toLowerCase();
  if (lower === "radar") return "Radar";
  if (lower === "pilot") return "Pilot";
  if (lower === "planner") return "Planner";
  return "Explainer";
}

function formatSigned(value: string): string {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "$0.00";
  const abs = `$${Math.abs(n).toFixed(2)}`;
  return n > 0 ? `+${abs}` : `-${abs}`;
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export type AdapterKind = "mock" | "http";

export interface CreateClientOptions {
  adapter?: AdapterKind;
  baseUrl?: string;
  accountId?: string;
  getToken?: () => Promise<string | null>;
}

/** Mock is the default: the UI is fully demonstrable with no backend. */
export function createFinkowClient(opts: CreateClientOptions = {}): FinkowClient {
  const adapter: AdapterKind =
    opts.adapter ?? (process.env.NEXT_PUBLIC_FINKOW_ADAPTER as AdapterKind | undefined) ?? "mock";
  if (adapter === "http") {
    return new HttpFinkowClient({
      baseUrl: opts.baseUrl ?? process.env.NEXT_PUBLIC_FINKOW_API_URL,
      accountId: opts.accountId,
      getToken: opts.getToken,
    });
  }
  return new MockFinkowClient();
}
