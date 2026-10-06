/**
 * Finkow v2 API client.
 *
 * The UI talks to this client only — never to fetch() directly — so the
 * product works end to end against a deterministic mock before the real
 * FastAPI backend lands. No invented endpoints: every method maps 1:1 to
 * docs/PRODUCT_REFRAME.md.
 *
 * Adapter selection: mock is the default (fully demonstrable, no backend).
 * Set NEXT_PUBLIC_FINKOW_ADAPTER=http with NEXT_PUBLIC_FINKOW_API_URL to
 * talk to the real API.
 */

export type RiskLevel = "low" | "medium" | "high";
export type AgentName = "Radar" | "Pilot" | "Planner" | "Explainer";

export interface Goal {
  id: string;
  text: string;
  createdAt: string;
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
  pulseText: string;
  pulseDetail: string;
  positions: Position[];
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
    return { id: `goal-${this.goalSeq}`, text: clean, createdAt: new Date().toISOString() };
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
/* HTTP adapter: talks to the real FastAPI backend when it lands.      */
/* ------------------------------------------------------------------ */

export class HttpFinkowClient implements FinkowClient {
  private readonly baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(`Finkow API ${res.status} on ${path}${detail ? `: ${detail}` : ""}`);
    }
    return (await res.json()) as T;
  }

  createGoal(text: string): Promise<Goal> {
    return this.request<Goal>("/goals", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  }

  getPlan(goalId: string): Promise<Plan> {
    return this.request<Plan>(`/goals/${encodeURIComponent(goalId)}/plan`);
  }

  getOpportunities(): Promise<Opportunity[]> {
    return this.request<{ opportunities: Opportunity[] }>("/radar/opportunities").then(
      (r) => r.opportunities,
    );
  }

  invest(opportunityId: string, amountUsd: number): Promise<InvestResult> {
    return this.request<InvestResult>("/portfolio/invest", {
      method: "POST",
      body: JSON.stringify({ opportunity_id: opportunityId, amount_usd: amountUsd }),
    });
  }

  getPortfolio(): Promise<Portfolio> {
    return this.request<Portfolio>("/portfolio");
  }

  explain(question: string): Promise<Explanation> {
    return this.request<Explanation>("/explain", {
      method: "POST",
      body: JSON.stringify({ question }),
    });
  }

  getActivity(): Promise<AgentEvent[]> {
    return this.request<{ events: AgentEvent[] }>("/agents/activity").then((r) => r.events);
  }
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export type AdapterKind = "mock" | "http";

/** Mock is the default: the UI is fully demonstrable with no backend. */
export function createFinkowClient(
  opts: { adapter?: AdapterKind; baseUrl?: string } = {},
): FinkowClient {
  const adapter: AdapterKind =
    opts.adapter ?? (process.env.NEXT_PUBLIC_FINKOW_ADAPTER as AdapterKind | undefined) ?? "mock";
  if (adapter === "http") {
    const baseUrl =
      opts.baseUrl ?? process.env.NEXT_PUBLIC_FINKOW_API_URL ?? "http://localhost:8000";
    return new HttpFinkowClient(baseUrl);
  }
  return new MockFinkowClient();
}
