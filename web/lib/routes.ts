// Where each model's outputs can be seen: its API routes and the pages that show it. The tier-leak tests request
// every one of these as every tier. Adding a model means adding it here, and a unit test fails until it is.
import type { ModelName } from "./registry";

export const MODEL_ROUTES: Record<ModelName, { api: string[]; pages: string[] }> = {
  bond_identity: { api: ["/api/v1/bonds/quotes"], pages: ["/bonds"] },
  bond_ns_curve: { api: ["/api/v1/bonds/curve"], pages: ["/", "/bonds"] },
  bond_liquidity: { api: ["/api/v1/bonds/liquidity"], pages: ["/bonds"] },
  bond_rv_zscores: { api: ["/api/v1/bonds/zscores"], pages: ["/bonds/zscores"] },
  bond_execution_gap: { api: ["/api/v1/bonds/execution-gap"], pages: ["/bonds/execution"] },
  bond_carry: { api: ["/api/v1/bonds/carry"], pages: ["/bonds/carry"] },
  cse_market_tape: { api: ["/api/v1/cse/market"], pages: ["/", "/cse"] },
  cse_security_metrics: { api: ["/api/v1/cse/shares"], pages: ["/cse", "/cse/shares"] },
  lk_savings_compare: { api: ["/api/v1/savings"], pages: ["/learn/savings"] },
};

// Every page of the site, for the checks that apply to all of them (no paid data for free visitors, ever).
export const ALL_PAGES = ["/", "/cse", "/cse/shares", "/bonds", "/bonds/zscores", "/bonds/execution", "/bonds/carry", "/learn", "/learn/savings", "/plans", "/methods", "/about", "/feedback", "/feedback/thanks", "/email/cse", "/email/bonds"];
