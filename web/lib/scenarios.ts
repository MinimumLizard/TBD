// "If yields changed": a bond's estimated price after a parallel change in its yield, from its modified duration
// and convexity (both published by bond_carry):  change / price ~= -D x dy + C x dy^2 / 2,  dy as a decimal.
// An education table, not a forecast: real prices also depend on the curve's shape and on trading.
export const SHIFTS_BP = [-200, -100, -50, -25, 25, 50, 100, 200] as const;

export function yieldScenarios(price: number, duration: number, convexity: number, shifts: readonly number[] = SHIFTS_BP) {
  return shifts.map((shiftBp) => {
    const dy = shiftBp / 10_000;
    const change = -duration * dy + 0.5 * convexity * dy * dy;
    return { shiftBp, change, price: price * (1 + change) };
  });
}
