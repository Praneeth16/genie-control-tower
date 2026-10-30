/** The CRO's screen: where the book stands, whether the data behind it is complete, and how far the
 *  AI can be trusted. Every number is read from the governed gold tables AS THE SIGNED-IN USER, so a
 *  regional head sees their regions and the totals say so. */
import { useEffect, useState } from "react";
import { Card, CardContent } from "@databricks/appkit-ui/react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { api, Overview as OverviewData } from "../api";
import { SectionTitle } from "./kit";

const inr = (v: unknown) =>
  v === null || v === undefined ? "—" : `INR ${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
const num = (v: unknown) => (v === null || v === undefined ? "—" : Number(v).toLocaleString("en-IN"));

function Kpi({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className="mt-1 text-2xl font-bold text-foreground">{value}</div>
        {note && <div className="mt-1 text-[11px] text-muted-foreground">{note}</div>}
      </CardContent>
    </Card>
  );
}

export function Overview() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.overview().then(setData).catch((e) => setError(String(e.message ?? e)));
  }, []);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!data) return <p className="text-sm text-muted-foreground">Loading the book…</p>;

  const k = data.kpis;
  const files = data.completeness.reduce((n, r) => n + Number(r.files ?? 0), 0);
  const reconciled = Number(data.completeness.find((r) => r.status === "RECONCILED")?.files ?? 0);
  const oohPct = data.conduct.contacts ? (100 * Number(data.conduct.out_of_hours_contacts)) / Number(data.conduct.contacts) : 0;
  const caught = data.quality.reduce((n, r) => n + Number(r.row_count ?? 0), 0);

  return (
    <div className="space-y-6">
      <section>
        <SectionTitle hint={`Month end ${k.as_of_month}. Read as you from the governed gold tables: if your entitlement covers some regions, these figures cover those regions.`}>
          Where the book stands
        </SectionTitle>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Kpi label="Gross NPA" value={`${k.gnpa_pct}%`} note={`${k.gnpa_pct_prev}% the month before`} />
          <Kpi label="Roll-forward rate" value={`${k.roll_forward_pct}%`} note="accounts moving to a worse bucket" />
          <Kpi label="Delinquent outstanding" value={inr(k.delinquent_outstanding_inr)} note={`${num(k.delinquent_accounts)} accounts on the worklist`} />
          <Kpi label="Out-of-hours contacts" value={num(data.conduct.out_of_hours_contacts)}
               note={`${oohPct.toFixed(1)}% of contacts in the last two months breached 08:00-19:00`} />
        </div>
      </section>

      <section>
        <SectionTitle hint="Each source sends a manifest of what it sent. Every file is reconciled: declared, landed, loaded, quarantined.">
          Can we trust the numbers?
        </SectionTitle>
        <Card>
          <CardContent className="space-y-2 p-4 text-sm">
            <div className="flex items-center gap-2">
              {reconciled === files ? <CheckCircle2 className="h-4 w-4 text-success" /> : <AlertTriangle className="h-4 w-4 text-warning" />}
              <span><b>{reconciled}</b> of <b>{files}</b> source files reconciled to their senders' manifests.</span>
            </div>
            {data.breaks.map((b) => (
              <div key={String(b.path)} className="ml-6 text-[13px] text-warning">
                {b.period}: <span className="font-mono">{b.path}</span> — {b.break_reason}
              </div>
            ))}
            <div className="ml-6 text-[13px] text-muted-foreground">
              {num(caught)} rows caught by quality rules, each kept with its reason rather than dropped:
              {" "}{data.quality.slice(0, 4).map((q) => `${q.reason} (${num(q.row_count)})`).join(", ")}.
            </div>
          </CardContent>
        </Card>
      </section>

      <section>
        <SectionTitle hint="The worklist the collections team is working, by region. Held accounts cannot be contacted while the borrower's grievance is open.">
          Where the risk sits
        </SectionTitle>
        <Card>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <tr><th className="p-3">Region</th><th className="p-3 text-right">Accounts</th><th className="p-3 text-right">Outstanding</th>
                    <th className="p-3 text-right">On hold (grievance)</th><th className="p-3 text-right">With a conduct flag</th></tr>
              </thead>
              <tbody>
                {data.worklist_by_region.map((r) => (
                  <tr key={String(r.region)} className="border-b border-border/60 last:border-0">
                    <td className="p-3 font-medium">{r.region}</td>
                    <td className="p-3 text-right">{num(r.accounts)}</td>
                    <td className="p-3 text-right">{inr(r.outstanding_inr)}</td>
                    <td className="p-3 text-right">{num(r.on_hold_grievance)}</td>
                    <td className="p-3 text-right">{num(r.with_conduct_flags)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </section>

      <section>
        <SectionTitle hint="Latest evaluation of the two AI steps, by a judge from a different model family. The AI reads and explains; it decides nothing.">
          How far the AI can be trusted
        </SectionTitle>
        <div className="grid gap-3 md:grid-cols-2">
          {["letter_triage", "case_brief"].map((c) => (
            <Card key={c}>
              <CardContent className="p-4 text-[13px]">
                <div className="mb-2 font-semibold">{c === "letter_triage" ? "Letter triage (in the pipeline)" : "Worklist briefs"}</div>
                {data.ai_quality.filter((r) => r.component === c && !["letters", "briefs", "errors"].includes(String(r.metric))).map((r) => (
                  <div key={String(r.metric)} className="flex justify-between border-b border-border/50 py-1 last:border-0">
                    <span className="text-muted-foreground">{String(r.metric).replace(/_/g, " ")}</span>
                    <span className="font-mono">{(100 * Number(r.value)).toFixed(1)}%</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <SectionTitle>How it gets here</SectionTitle>
        <ol className="grid gap-2 md:grid-cols-3">
          {data.journey.map((j, i) => (
            <li key={j.stage} className="rounded border border-border bg-card p-3 text-[13px]">
              <span className="font-semibold text-primary">{i + 1}. {j.stage}</span>
              <div className="mt-1 text-muted-foreground">{j.what}</div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
