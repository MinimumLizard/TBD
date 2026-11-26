// The portfolio lab's example portfolio and the review schedules shown beside it (decisions 0024, 0026, 0027).

/** The example portfolio: minimum variance, 15 names, reviewed twice a year. */
export const FLAGSHIP = { policy: "half_yearly", portfolio: "min_variance_15" } as const;
export const SCHEDULES = ["half_yearly", "quarterly", "dynamic"] as const;
