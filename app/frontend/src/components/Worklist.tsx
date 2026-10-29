/** The Head of Collections' screen: the accounts to work, in order, with the reasons; and the case
 *  record where an officer acts. The list comes from Lakebase (refreshed from gold every cycle), scoped
 *  to the regions Unity Catalog grants the signed-in user. Status, owner, notes and next date are the
 *  officer's, and no refresh overwrites them; every change lands in the case history. */
import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, CardContent } from "@databricks/appkit-ui/react";
import { AlertTriangle, Sparkles } from "lucide-react";
import { api, CaseDetail, CaseList, CaseRow } from "../api";
import { SectionTitle } from "./kit";

const STATUSES = ["new", "in_progress", "promise_to_pay", "on_hold", "resolved", "closed"];
// Suggestions that map to an action needing approval. hold_contact and tele_calling_reminder are worked
// on the case itself.
const ACTIONS: Record<string, string> = {
  assign_recovery_agency: "assign_recovery_agency",
  offer_settlement: "offer_settlement",
  schedule_field_visit: "schedule_field_visit",
};
const inr = (v: unknown) => `INR ${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

function CasePanel({ id, onChanged }: { id: number; onChanged: () => void }) {
  const [d, setD] = useState<CaseDetail | null>(null);
  const [form, setForm] = useState({ status: "", owner: "", notes: "", next_action_date: "" });
  const [msg, setMsg] = useState<string | null>(null);
  // Agency allocation and field visits name the agent who will act. The bank's controls check that agent's
  // conduct certification, so an uncertified or lapsed agent is refused before anyone approves.
  const [agent, setAgent] = useState("");

  const load = useCallback(() => {
    api.caseDetail(id).then((x) => {
      setD(x);
      setForm({ status: x.case.status, owner: x.case.owner ?? "", notes: x.case.notes ?? "",
                next_action_date: x.case.next_action_date ?? "" });
    }).catch((e) => setMsg(String(e.message ?? e)));
  }, [id]);
  useEffect(load, [load]);

  if (!d) return <p className="text-sm text-muted-foreground">{msg ?? "Loading case…"}</p>;
  const c = d.case;

  const save = () =>
    api.updateCase(id, { ...form, next_action_date: form.next_action_date || null })
      .then(() => { setMsg("Saved. The change is in the case history."); load(); onChanged(); })
      .catch((e) => setMsg(String(e.message ?? e)));

  const propose = (action_type: string) =>
    api.act({ action_type, subject: c.loan_account_id, case_id: c.case_id,
              payload: { reason: c.ai_explanation ?? c.recommended_treatment, amount_inr: Number(c.outstanding_principal),
                         ...(agent ? { agent_id: agent.trim().toUpperCase() } : {}) } })
      .then((r) => { setMsg(r.guardrail.passed
          ? `Proposed. It now needs approval by someone holding the ${r.approver_role ?? "required"} role, and not by you.`
          : `The bank's controls refused it: ${r.guardrail.breaches.join("; ")}`); load(); })
      .catch((e) => setMsg(String(e.message ?? e)));

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-semibold">{c.loan_account_id}</span>
          <Badge variant="outline">#{c.priority_rank}</Badge>
          <Badge variant="outline">{c.region} · {c.product_code}</Badge>
        </div>
        <div className="mt-1 text-[13px] text-muted-foreground">
          {c.dpd_days} days past due ({c.dpd_bucket}) · {inr(c.outstanding_principal)} outstanding · score {c.priority_score}
        </div>
      </div>

      <div className="text-[13px]">
        <div className="mb-1 font-semibold">Why it is here</div>
        <ul className="list-disc pl-5">{c.drivers.map((x) => <li key={x}>{x}</li>)}</ul>
        {c.conduct_flags.length > 0 && (
          <div className="mt-2 rounded border border-warning/40 bg-warning/10 p-2 text-warning">
            <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />{c.conduct_flags.join(" · ")}
          </div>
        )}
        <div className="mt-2"><span className="font-semibold">Bank rule:</span> {c.recommended_treatment}</div>
      </div>

      {c.ai_explanation && (
        <div className="rounded border border-border bg-secondary/40 p-3 text-[13px]">
          <div className="mb-1 flex items-center gap-1 font-semibold"><Sparkles className="h-3.5 w-3.5" /> AI brief</div>
          {c.ai_explanation}
          <div className="mt-1 text-[11px] text-muted-foreground">Suggested: {c.ai_recommended_action}. A suggestion; you decide.</div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 text-[13px]">
        <label>Status
          <select className="mt-1 w-full rounded border border-border bg-background p-1.5" value={form.status}
                  onChange={(e) => setForm({ ...form, status: e.target.value })}>
            {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </select>
        </label>
        <label>Owner
          <input className="mt-1 w-full rounded border border-border bg-background p-1.5" value={form.owner}
                 onChange={(e) => setForm({ ...form, owner: e.target.value })} />
        </label>
        <label>Next action date
          <input type="date" className="mt-1 w-full rounded border border-border bg-background p-1.5" value={form.next_action_date}
                 onChange={(e) => setForm({ ...form, next_action_date: e.target.value })} />
        </label>
        <label className="col-span-2">Notes
          <textarea className="mt-1 w-full rounded border border-border bg-background p-1.5" rows={2} value={form.notes}
                    onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </label>
      </div>
      <label className="block text-[13px]">Agent for an allocation or visit (e.g. AG007)
        <input className="mt-1 w-40 rounded border border-border bg-background p-1.5 font-mono" value={agent}
               onChange={(e) => setAgent(e.target.value)} />
      </label>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={save}>Save case</Button>
        {Object.keys(ACTIONS).map((a) => (
          <Button key={a} size="sm" variant="outline" onClick={() => propose(a)}>Propose {a.replace(/_/g, " ")}</Button>
        ))}
      </div>
      {msg && <p className="text-[13px] text-muted-foreground">{msg}</p>}

      {d.actions.length > 0 && (
        <div className="text-[13px]">
          <div className="mb-1 font-semibold">Actions on this case</div>
          {d.actions.map((a) => (
            <div key={a.id}>#{a.id} {a.action_type} — {a.status} (raised by {a.requested_by})</div>
          ))}
        </div>
      )}

      <div className="text-[12px]">
        <div className="mb-1 font-semibold">History</div>
        <div className="max-h-56 overflow-auto rounded border border-border">
          {d.history.map((h, i) => (
            <div key={i} className="border-b border-border/50 px-2 py-1 last:border-0">
              <span className="font-mono text-muted-foreground">{h.changed_at.slice(0, 16).replace("T", " ")}</span>{" "}
              <b>{h.field}</b> {h.old_value ?? "∅"} → {h.new_value ?? "∅"}{" "}
              <span className="text-muted-foreground">by {h.changed_by} ({h.change_source})</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function Worklist() {
  const [list, setList] = useState<CaseList | null>(null);
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.cases(status || undefined).then(setList).catch((e) => setError(String(e.message ?? e)));
  }, [status]);
  useEffect(load, [load]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!list) return <p className="text-sm text-muted-foreground">Loading the worklist…</p>;

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_420px]">
      <section>
        <SectionTitle hint={`${list.source}. Your regions: ${list.regions.join(", ") || "none"}.`}>
          Collections worklist
        </SectionTitle>
        <div className="mb-2 flex flex-wrap gap-1.5 text-[12px]">
          {["", ...STATUSES].map((s) => (
            <button key={s || "all"} onClick={() => setStatus(s)}
                    className={`rounded border px-2 py-0.5 ${status === s ? "border-primary text-primary" : "border-border text-muted-foreground"}`}>
              {s ? `${s.replace(/_/g, " ")} (${list.by_status[s] ?? 0})` : "all"}
            </button>
          ))}
        </div>
        <Card>
          <CardContent className="p-0">
            <table className="w-full text-[13px]">
              <thead className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <tr><th className="p-2">#</th><th className="p-2">Account</th><th className="p-2">Region</th>
                    <th className="p-2 text-right">DPD</th><th className="p-2 text-right">Outstanding</th>
                    <th className="p-2">Rule</th><th className="p-2">Status</th></tr>
              </thead>
              <tbody>
                {list.cases.map((c: CaseRow) => (
                  <tr key={c.case_id} onClick={() => setSelected(c.case_id)}
                      className={`cursor-pointer border-b border-border/50 last:border-0 hover:bg-secondary/40 ${selected === c.case_id ? "bg-secondary/60" : ""}`}>
                    <td className="p-2">{c.priority_rank}</td>
                    <td className="p-2 font-mono">{c.loan_account_id}{c.conduct_flags.length > 0 && <AlertTriangle className="ml-1 inline h-3 w-3 text-warning" />}</td>
                    <td className="p-2">{c.region}</td>
                    <td className="p-2 text-right">{c.dpd_days}</td>
                    <td className="p-2 text-right">{inr(c.outstanding_principal)}</td>
                    <td className="p-2 text-muted-foreground">{c.recommended_treatment}</td>
                    <td className="p-2">{c.status.replace(/_/g, " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </section>
      <aside>
        <Card><CardContent className="p-4">
          {selected ? <CasePanel id={selected} onChanged={load} /> :
            <p className="text-sm text-muted-foreground">Select an account to see why it is on the list and to work it.</p>}
        </CardContent></Card>
      </aside>
    </div>
  );
}
