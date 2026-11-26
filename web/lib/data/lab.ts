// The portfolio lab (cse_lab_backtest; Pro, decision 0027): the example portfolio the written rules chose, how it
// would have done since the first date the rules could run, and how it is kept in shape. Read only through the tier
// check; every number is a stored output of the model, on its neutral settings (Rs 1 mn, no personal settings).
import "server-only";

import { readOutput } from "../db";
import type { Viewer } from "../entitlements";
import { FLAGSHIP } from "../lab-display";
import { type Result, withModel } from "./common";


export interface LabHolding {
  symbol: string;
  weight: number;
  sector: string | null;
  volatility: number | null;
  avg_correlation: number | null;
  at_cap: boolean;
}

export interface LabSummary {
  policy: string;
  portfolio: string;
  start_date: string;
  end_date: string;
  total_return: number | null;
  volatility: number | null;
  max_drawdown: number | null;
  costs: number | null;
  turnover: number | null;
  n_rebalances: number | null;
}

export interface LabEvent {
  session_date: string;
  kind: string; // inception | scheduled | threshold | drift
  names_in: string;
  names_out: string;
  turnover: number;
  cost: number;
}

export interface Lab {
  formedOn: string | null; // the review whose weights are held
  holdings: LabHolding[];
  summaries: LabSummary[]; // the example under each schedule, and the market and bills beside it
  nav: { session_date: string; portfolio: string; nav: number }[]; // the example, the market, bills
  events: LabEvent[]; // the example's reviews and drift trades
}

export async function lab(viewer: Viewer): Promise<Result<Lab>> {
  return withModel(viewer, "cse_lab_backtest", async (g) => {
    const { policy, portfolio } = FLAGSHIP;
    const [latest] = await readOutput<{ as_of: string }>(g, "models.cse_bt_target", {
      columns: ["as_of"], where: "policy = ? and portfolio = ? and applied", params: [policy, portfolio],
      orderBy: "as_of desc", limit: 1,
    });
    const [holdings, summaries, nav, events] = await Promise.all([
      latest
        ? readOutput<LabHolding>(g, "models.cse_bt_target", {
            columns: ["symbol", "weight", "sector", "volatility", "avg_correlation", "at_cap"],
            where: "as_of = ? and policy = ? and portfolio = ? and applied", params: [latest.as_of, policy, portfolio],
            orderBy: "weight desc",
          })
        : Promise.resolve([]),
      readOutput<LabSummary>(g, "models.cse_bt_summary", {
        columns: ["policy", "portfolio", "start_date", "end_date", "total_return", "volatility", "max_drawdown", "costs",
                  "turnover", "n_rebalances"],
        where: "portfolio in (?, 'market', 'bills')", params: [portfolio],
      }),
      readOutput<{ session_date: string; portfolio: string; nav: number }>(g, "models.cse_bt_nav", {
        columns: ["session_date", "portfolio", "nav"], where: "policy = ? and portfolio in (?, 'market', 'bills')",
        params: [policy, portfolio], orderBy: "session_date",
      }),
      readOutput<LabEvent>(g, "models.cse_bt_event", {
        columns: ["session_date", "kind", "names_in", "names_out", "turnover", "cost"],
        where: "policy = ? and portfolio = ?", params: [policy, portfolio], orderBy: "session_date",
      }),
    ]);
    return { formedOn: latest?.as_of ?? null, holdings, summaries, nav, events };
  });
}
