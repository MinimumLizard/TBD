import Link from "next/link";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import DealingsTable from "@/components/DealingsTable";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import PreviewNote from "@/components/PreviewNote";
import StatTile from "@/components/StatTile";
import Term from "@/components/Term";
import { dealingNames, flows, recentDealings } from "@/lib/data/dealings";
import { WINDOWS, flowWindow } from "@/lib/dealings-display";
import { date, int, lkr } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

const SHOWN_COMPANIES = 25;
const SHOWN_DEALINGS = 30;
const rs = (v: number) => (v === 0 ? "0" : lkr(v)); // no dealings on that side: a plain 0, not "Rs 0.00 mn"

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("dealings.title") };
}

export default async function DealingsPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const [t, viewer, params] = await Promise.all([getTranslations(), getViewer(), searchParams]);
  const window = flowWindow(params.window);
  const [recent, flow] = await Promise.all([recentDealings(viewer, SHOWN_DEALINGS), flows(viewer, window)]);
  const f = flow.data;
  const largeNames = (await dealingNames(viewer, (f?.large ?? []).map((d) => d.transaction_id))).data ?? new Map();
  const shareHref = (code: string) => `/cse/shares/${encodeURIComponent(`${code}.N0000`)}`;
  const companies = f?.companies ?? [];
  return (
    <>
      <h1>{t("dealings.title")}</h1>
      <p className="lead">{t("dealings.intro")}</p>
      <p className="small muted">{t("dealings.namesNote")}</p>

      <h2>{t("dealings.recent")}</h2>
      {!recent.access.allowed ? (
        <Locked access={recent.access} />
      ) : (recent.data ?? []).length === 0 ? (
        <p className="muted">{t("dealings.none")}</p>
      ) : (
        <>
          <DealingsTable rows={recent.data ?? []} showCompany />
          <p className="small muted">
            {t("dealings.recentNote", { count: (recent.data ?? []).length })} {t("dealings.sideOtherNote")}
          </p>
        </>
      )}

      <h2 id="flows">{t("dealings.flows")}</h2>
      {!flow.access.allowed ? (
        <Locked access={flow.access} />
      ) : !f?.summary ? (
        <p className="muted">{t("common.noData")}</p>
      ) : (
        <>
          <PreviewNote access={flow.access} />
          <AsOf day={f.summary.as_of} calendar="cse" preview />
          <div className="tiles">
            <StatTile label={t("dealings.summaryDealings")} value={int(f.summary.n_dealings)}
                      note={f.first_date ? t("dealings.summaryDealingsNote", { date: date(f.first_date) }) : null} />
            <StatTile label={t("dealings.summaryLag")}
                      value={f.summary.lag_median != null ? t("dealings.lagValue", { n: f.summary.lag_median }) : "—"} />
          </div>
          <nav className="tabs" aria-label={t("dealings.windowLabel")}>
            {WINDOWS.map((w) => (
              <Link key={w} href={`/cse/dealings?window=${w}#flows`} aria-current={w === window ? "page" : undefined}>
                {t(`dealings.windows.${w}` as never)}
              </Link>
            ))}
          </nav>
          <p>{t("dealings.flowsIntro", { window: t(`dealings.windows.${window}` as never), date: date(f.summary.as_of) })}</p>
          {companies.length === 0 ? (
            <p className="muted">{t("dealings.noFlows")}</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{t("dealings.company")}</th>
                    <th className="num">{t("dealings.purchases")}</th>
                    <th className="num">{t("dealings.disposals")}</th>
                    <th className="num">{t("dealings.net")}</th>
                    <th className="num">{t("dealings.purchasers")}</th>
                    <th className="num">{t("dealings.disposers")}</th>
                    <th className="num">{t("dealings.transactions")}</th>
                    <th><Term id="cluster">{t("dealings.cluster")}</Term></th>
                  </tr>
                </thead>
                <tbody>
                  {companies.slice(0, SHOWN_COMPANIES).map((c) => (
                    <tr key={c.symbol}>
                      <td>
                        <Link href={shareHref(c.symbol)}>{c.symbol}</Link>
                        <span className="sub">{c.company}</span>
                      </td>
                      <td className="num">{rs(c.purchase_value)}</td>
                      <td className="num">{rs(c.disposal_value)}</td>
                      <td className="num">{lkr(c.net_value)}</td>
                      <td className="num">{int(c.n_purchasers)}</td>
                      <td className="num">{int(c.n_disposers)}</td>
                      <td className="num">{int(c.n_transactions)}</td>
                      <td>{c.cluster ? t("dealings.cluster") : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="small muted">
            {companies.length > SHOWN_COMPANIES && <>{t("dealings.more", { count: companies.length - SHOWN_COMPANIES })} </>}
            {t("dealings.clusterNote")}
          </p>

          <h3>{t("dealings.large")}</h3>
          {f.large.length === 0 ? (
            <p className="muted">{t("dealings.noLarge", { date: date(f.summary.as_of) })}</p>
          ) : (
            <>
              <p>{t("dealings.largeIntro", { date: date(f.summary.as_of) })}</p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>{t("dealings.date")}</th>
                      <th>{t("dealings.company")}</th>
                      <th>{t("dealings.side")}</th>
                      <th className="num">{t("dealings.value")}</th>
                      <th>{t("dealings.director")}</th>
                      <th>{t("dealings.account")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {f.large.map((d) => (
                      <tr key={d.transaction_id}>
                        <td>{date(d.deal_date)}</td>
                        <td>
                          <Link href={shareHref(d.symbol)}>{d.symbol}</Link>
                          {f.names[d.symbol] && <span className="sub">{f.names[d.symbol]}</span>}
                        </td>
                        <td>{t(`dealings.sides.${d.side}` as never)}</td>
                        <td className="num">{lkr(d.value)}</td>
                        <td className="small">{largeNames.get(d.transaction_id)?.director ?? ""}</td>
                        <td className="small">
                          {d.related_account ? largeNames.get(d.transaction_id)?.account ?? "" : t("dealings.accounts.own")}
                          <span className="sub">{t(`dealings.actorTypes.${d.actor_type}` as never)}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {f.accounts.length > 0 && (
            <>
              <h3>{t("dealings.accountsTitle")}</h3>
              <p>{t("dealings.accountsIntro", { window: t(`dealings.windows.${window}` as never), date: date(f.summary.as_of) })}</p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>{t("dealings.accountName")}</th>
                      <th className="num">{t("dealings.purchases")}</th>
                      <th className="num">{t("dealings.disposals")}</th>
                      <th className="num">{t("dealings.net")}</th>
                      <th className="num">{t("dealings.transactions")}</th>
                      <th>{t("dealings.companiesDealt")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {f.accounts.map((a) => (
                      <tr key={a.actor_key}>
                        <td className="names">
                          {a.actor}
                          <span className="sub">{t(`dealings.actorTypes.${a.actor_type}` as never)}</span>
                        </td>
                        <td className="num">{rs(a.purchase_value)}</td>
                        <td className="num">{rs(a.disposal_value)}</td>
                        <td className="num">{lkr(a.net_value)}</td>
                        <td className="num">{int(a.n_transactions)}</td>
                        <td className="small">
                          {(JSON.parse(a.companies) as [string, number][]).map(([code], i) => (
                            <span key={code}>{i > 0 && ", "}<Link href={shareHref(code)}>{code}</Link></span>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
      <ModelFooter models={[...(recent.access.allowed ? ["cse_dealings" as const] : []),
                            ...(flow.access.allowed ? ["cse_flows" as const] : [])]} />
    </>
  );
}
