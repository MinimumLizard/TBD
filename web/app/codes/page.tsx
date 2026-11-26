import Link from "next/link";
import { getTranslations } from "next-intl/server";

import Bolt from "@/components/Bolt";
import LockedLine from "@/components/LockedLine";
import PageHead from "@/components/PageHead";
import { bondHref, bondName } from "@/lib/bond-display";
import { CODES } from "@/lib/codes";
import { companyName } from "@/lib/cse-display";
import { bondReference, bondZscores } from "@/lib/data/bonds";
import { securityNames, shares } from "@/lib/data/cse";
import { flows, recentDealings } from "@/lib/data/dealings";
import { lab } from "@/lib/data/lab";
import { savingsOverview } from "@/lib/data/savings";
import { FLAGSHIP } from "@/lib/lab-display";
import { date, lkr, num, pct, percent } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

const PREVIEW = 5; // rows in each code's preview

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("codes.title") };
}

/** A search box that opens the page holding the full list. */
function Search({ action, placeholder, label }: { action: string; placeholder: string; label: string }) {
  return (
    <form className="code-search" method="get" action={action} role="search">
      <label>
        <span className="visually-hidden">{placeholder}</span>
        <input type="search" name="q" placeholder={placeholder} autoComplete="off" />
      </label>
      <button type="submit" className="button">{label}</button>
    </form>
  );
}

// Cheat codes (decision 0027): public data most people do not know is public. Each is a drop-down: one line closed;
// open, a search and a short live preview, read through the same tier check as the full page (a taste for free).
export default async function CodesPage() {
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [dealings, flow, market, names, labResult, savings, z, bonds] = await Promise.all([
    recentDealings(viewer, PREVIEW), flows(viewer, 30), shares(viewer), securityNames(viewer), lab(viewer),
    savingsOverview(viewer), bondZscores(viewer), bondReference(viewer),
  ]);
  const name = (symbol: string) => companyName(names.data?.get(symbol)?.name) ?? symbol.replace(/\.N0000$/, "");
  const largest = (market.data?.rows ?? []).filter((r) => r.symbol.endsWith(".N0000") && r.market_cap)
    .sort((a, b) => (b.market_cap ?? 0) - (a.market_cap ?? 0)).slice(0, 4);
  const go = t("codes.go");

  const body: Record<string, React.ReactNode> = {
    dealings: (
      <>
        <Search action="/cse/dealings" placeholder={t("dealings.searchPlaceholder")} label={go} />
        {dealings.access.allowed && (dealings.data ?? []).length > 0 && (
          <ul className="mini">
            {dealings.data!.map((d) => (
              <li key={d.transaction_id}>
                <span><Link href={`/cse/shares/${encodeURIComponent(`${d.symbol}.N0000`)}`}>{d.symbol}</Link> · {d.director ?? ""}</span>
                <span className={d.side === "purchase" ? "up" : d.side === "disposal" ? "down" : "flat"}>
                  {t(`dealings.sides.${d.side}` as never)} {lkr(d.value)}
                </span>
                <span className="muted">{date(d.deal_date)}</span>
              </li>
            ))}
          </ul>
        )}
      </>
    ),
    flows: (
      <>
        <Search action="/cse/dealings" placeholder={t("codes.flowsPlaceholder")} label={go} />
        {flow.access.allowed && flow.data?.summary ? (
          <>
            {flow.access.delayDays > 0 && <p className="small muted">{t("codes.weekLate", { date: date(flow.data.summary.as_of) })}</p>}
            <ul className="mini">
              {[...flow.data.companies].sort((a, b) => Math.abs(b.net_value) - Math.abs(a.net_value)).slice(0, PREVIEW).map((c) => (
                <li key={c.symbol}>
                  <span><Link href={`/cse/shares/${encodeURIComponent(`${c.symbol}.N0000`)}`}>{c.symbol}</Link> · {c.company}</span>
                  <span className={c.net_value >= 0 ? "up" : "down"}>{t("codes.net")} {lkr(c.net_value)}</span>
                  <span className="muted">{t("codes.accounts", { n: c.n_purchasers + c.n_disposers })}</span>
                </li>
              ))}
            </ul>
          </>
        ) : !flow.access.allowed ? <LockedLine access={flow.access} what={t("codes.flows.title")} /> : null}
      </>
    ),
    owners: (
      <>
        <Search action="/search" placeholder={t("codes.companyPlaceholder")} label={go} />
        {largest.length > 0 && (
          <p className="chips">
            {largest.map((r) => (
              <Link key={r.symbol} className="chip-link" href={`/cse/shares/${encodeURIComponent(r.symbol)}#owners`}>{name(r.symbol)}</Link>
            ))}
          </p>
        )}
        <p className="small muted">{t("codes.ownersNote")}</p>
      </>
    ),
    groups: (
      <>
        <Search action="/search" placeholder={t("codes.companyPlaceholder")} label={go} />
        <p className="small muted">{t("codes.groupsNote")}</p>
      </>
    ),
    totalReturn: <p className="small muted">{t("codes.totalReturnNote")}</p>,
    lab: labResult.access.allowed && labResult.data ? (() => {
      const flag = labResult.data.summaries.find((s) => s.policy === FLAGSHIP.policy && s.portfolio === FLAGSHIP.portfolio);
      const mk = labResult.data.summaries.find((s) => s.policy === FLAGSHIP.policy && s.portfolio === "market");
      return flag ? (
        <dl className="mini-stats">
          <div><dt>{t("lab.tiles.return")}</dt><dd>{pct(flag.total_return, 1)}</dd><dd className="muted">ASPI {pct(mk?.total_return, 1)}</dd></div>
          <div><dt>{t("lab.tiles.swings")}</dt><dd>{percent((flag.volatility ?? 0) * 100, 1)}</dd><dd className="muted">ASPI {percent((mk?.volatility ?? 0) * 100, 1)}</dd></div>
          <div><dt>{t("lab.tiles.fall")}</dt><dd>{pct(flag.max_drawdown, 1)}</dd><dd className="muted">ASPI {pct(mk?.max_drawdown, 1)}</dd></div>
        </dl>
      ) : null;
    })() : !labResult.access.allowed ? <LockedLine access={labResult.access} what={t("codes.lab.title")} /> : null,
    fd: savings.access.allowed && savings.data ? (() => {
      const r = [...savings.data.rates].reverse().find((x) => x.fd_rate_pct != null && x.inflation_yoy != null);
      if (!r) return null;
      const after = (r.fd_rate_pct ?? 0) * (1 - r.fd_tax_pct / 100);
      return (
        <dl className="mini-stats">
          <div><dt>{t("codes.fdRate")}</dt><dd>{num(r.fd_rate_pct, 2)}%</dd></div>
          <div><dt>{t("codes.fdAfterTax")}</dt><dd>{num(after, 2)}%</dd></div>
          <div><dt>{t("codes.inflation")}</dt><dd>{num((r.inflation_yoy ?? 0) * 100, 1)}%</dd></div>
        </dl>
      );
    })() : null,
    bonds: z.access.allowed && z.data ? (
      <>
        {z.access.delayDays > 0 && z.data.date && <p className="small muted">{t("codes.daysLate", { n: z.access.delayDays, date: date(z.data.date) })}</p>}
        <ul className="mini">
          {[...z.data.bonds].sort((a, b) => Math.abs(b.zscore) - Math.abs(a.zscore)).slice(0, 3).map((b) => (
            <li key={b.isin}>
              <span><Link href={bondHref(b.isin)}>{bondName(b.isin, bonds.data)}</Link></span>
              <span>z {num(b.zscore, 2)}</span>
              <span className="muted">{num(b.residual_bp, 1)} bp</span>
            </li>
          ))}
        </ul>
      </>
    ) : !z.access.allowed ? <LockedLine access={z.access} what={t("codes.bonds.title")} /> : null,
  };

  return (
    <>
      <PageHead eyebrow={t("codes.eyebrow")} title={t("codes.title")} lead={t("codes.lead")} />
      <div className="codes">
        {CODES.map((c) => (
          <details key={c.key} className="code" id={c.key}>
            <summary>
              <span className="code-icon"><Bolt size={16} /></span>
              <span className="code-text">
                <span className="code-title">
                  {t(`codes.${c.key}.title` as never)}
                  {c.tier !== "free" && <span className={`tier-pill ${c.tier}`}>{t(`tiers.${c.tier}`)}</span>}
                </span>
                <span className="code-line">{t(`codes.${c.key}.line` as never)}</span>
              </span>
              <span className="s-chev" aria-hidden="true" />
            </summary>
            <div className="code-body">
              {body[c.key]}
              <Link className="more" href={c.href}>{t("codes.open")} →</Link>
            </div>
          </details>
        ))}
      </div>
      <p className="small muted">{t("codes.note")}</p>
    </>
  );
}
