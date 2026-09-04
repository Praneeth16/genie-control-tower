/** The unstructured lane, as chat turns: what borrowers actually said, and a reply grounded in it.
 *
 *  Why this lane earns its place: a complaint row says `severity = 'Critical'`. The letter says the
 *  agent came at 9:15 pm and shouted the borrower's name so the neighbours could hear. The reply the
 *  agent drafts is grounded in the second, which is why it reads like an answer rather than a template.
 */
import { useEffect, useState } from "react";
import { Button, Card, CardContent } from "@databricks/appkit-ui/react";
import { FileText, Loader2, PenLine } from "lucide-react";
import { api, Draft, Evidence, Guardrail, SearchResult } from "../../api";
import { ErrorText, SectionTitle } from "../kit";
import { GuardrailVerdict } from "../Guardrails";

/** Semantic search results. Search runs as the application's service principal over an index that is
 *  a COPY of the letters, so every hit's record is then re-read under the caller's own entitlements —
 *  which is why a hit can come back marked outside your scope rather than simply missing. */
export function SearchTurn({
  hits,
  onOpenComplaint,
}: {
  hits: SearchResult;
  onOpenComplaint: (complaintId: string) => void;
}) {
  if (!hits.ok) {
    return (
      <Card className="border-warning/40">
        <CardContent className="p-4 text-[12px] leading-relaxed text-warning">{hits.note}</CardContent>
      </Card>
    );
  }
  return (
    <Card className="border-border">
      <CardContent className="space-y-2 p-4">
        <SectionTitle hint="Vector Search over 713 letters. The index is queried as the application's service principal and never granted to end users; every record it finds is then re-read under YOUR entitlements. Retrieval locates the letter, governance still decides whether you may read it.">
          What borrowers actually said
        </SectionTitle>
        <p className="text-[12px] leading-relaxed text-muted-foreground">{hits.note}</p>
        <div className="space-y-2">
          {hits.hits.map((h, i) => (
            <div
              // Index-suffixed: policy documents carry no complaint_id, so two of them sharing a snippet
              // prefix produced duplicate keys and React reused the wrong node.
              key={`${h.complaint_id ?? "doc"}-${i}`}
              className={
                "rounded border px-3 py-2 " +
                (h.outside_your_scope
                  ? "border-warning/40 bg-warning/10"
                  : "border-border bg-background")
              }
            >
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                <span className="font-semibold text-foreground">
                  {h.complaint_id ?? "policy document"}
                </span>
                {h.rbi_ground && <span className="rounded bg-secondary px-1.5 py-0.5">{h.rbi_ground}</span>}
                {h.city && <span>{h.city}</span>}
                <span className="tabular-nums">score {h.score.toFixed(3)}</span>
                {h.record?.status ? <span>· {String(h.record.status)}</span> : null}
                {h.record?.escalated_to_ombudsman === "true" ||
                h.record?.escalated_to_ombudsman === true ? (
                  <span className="font-semibold text-destructive">ombudsman</span>
                ) : null}
                {h.complaint_id && !h.outside_your_scope && (
                  <button
                    onClick={() => onOpenComplaint(h.complaint_id as string)}
                    className="ml-auto rounded border border-border px-1.5 py-0.5 hover:bg-secondary"
                  >
                    open this complaint
                  </button>
                )}
              </div>
              {h.snippet && (
                <p className="mt-1 text-xs leading-relaxed text-foreground/85">{h.snippet}</p>
              )}
              {h.outside_your_scope && (
                <p className="mt-1 text-[11px] font-semibold text-warning">
                  Outside your entitlement — the letter exists and matched, but the record is not yours
                  to read. This is not "no such complaint".
                </p>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

/** One complaint opened: the structured record, the customer's own words, and a drafted reply. */
export function EvidenceTurn({
  evidence,
  onActed,
}: {
  evidence: Evidence;
  onActed: () => void;
}) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [outbound, setOutbound] = useState<{ name: string; path: string; size: number }[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<{ id: number; guardrail: Guardrail } | null>(null);

  // Only after a draft exists is the volume listing worth showing: it is the proof the write landed.
  useEffect(() => {
    if (!draft?.ok) return;
    api.outbound().then((r) => setOutbound(r.documents)).catch(() => setOutbound([]));
  }, [draft]);

  const rec = evidence.record;

  async function makeDraft() {
    setBusy("draft");
    setError(null);
    try {
      setDraft(await api.draft(evidence.complaint_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function proposeDispatch() {
    if (!draft?.action_draft) return;
    setBusy("propose");
    setError(null);
    try {
      const d = draft.action_draft;
      const r = await api.act({
        action_type: d.action_type,
        subject: d.subject,
        payload: d.payload,
        region: d.region,
        level: d.level,
      });
      setVerdict({ id: r.action.id, guardrail: r.guardrail });
      onActed();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  if (!evidence.found || !rec) {
    return (
      <Card className="border-warning/40">
        <CardContent className="p-4 text-xs leading-relaxed text-warning">
          {evidence.note ?? `No record for ${evidence.complaint_id}.`}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 lg:grid-cols-2">
        <Card className="border-border">
          <CardContent className="space-y-2 p-4">
            <SectionTitle hint="Letters, internal compliance notes and agency contracts live in a Unity Catalog volume, parsed into a Delta table in the same schema — so the row filters and column masks that govern the tables govern the documents too.">
              What our systems recorded
            </SectionTitle>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[12px]">
              {[
                ["complaint", rec.complaint_id],
                ["received", rec.received_date],
                ["ground (RBI)", rec.rbi_category],
                ["category", rec.category_name],
                ["severity", rec.severity],
                ["status", rec.status],
                ["product", rec.product_code],
                ["city", rec.city],
                ["SLA days", rec.sla_days],
                ["days to resolve", rec.days_to_resolve],
                ["SLA breached", rec.sla_breached],
                ["ombudsman", rec.escalated_to_ombudsman],
                ["customer", rec.customer_id],
              ].map(([k, v]) => (
                <div key={String(k)} className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="font-mono text-foreground">{v ?? "—"}</dd>
                </div>
              ))}
            </dl>
            <p className="pt-1 text-[11px] leading-relaxed text-muted-foreground">
              The customer id is pseudonymised for you unless you are cleared to read raw identifiers.
              It is a stable token, so joins still work.
            </p>
          </CardContent>
        </Card>

        <Card className="border-border">
          <CardContent className="space-y-2 p-4">
            <div className="flex items-center gap-2">
              <FileText className="h-3.5 w-3.5 text-primary" />
              <SectionTitle>What the customer wrote</SectionTitle>
            </div>
            {rec.document_text ? (
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded border border-border bg-background/60 p-2 text-[11px] leading-relaxed text-foreground/85">
                {rec.document_text}
              </pre>
            ) : (
              <p className="text-xs text-muted-foreground">No letter on file for this complaint.</p>
            )}
            {rec.file_path && (
              <p className="font-mono text-[11px] text-muted-foreground">{rec.file_path}</p>
            )}
          </CardContent>
        </Card>
      </div>

      {error && <ErrorText>{error}</ErrorText>}

      <Card className="border-border">
        <CardContent className="space-y-3 p-4">
          <SectionTitle hint="Grounded in the record AND the letter, so the reply answers what they actually said. It is written to the volume as an UNSIGNED draft: dispatching it to a customer is a separate act needing a named officer's approval.">
            Draft a reply
          </SectionTitle>
          <Button size="sm" onClick={makeDraft} disabled={busy !== null}>
            {busy === "draft" ? (
              <>
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> Drafting…
              </>
            ) : (
              <>
                <PenLine className="mr-1.5 h-3.5 w-3.5" /> Draft the resolution letter
              </>
            )}
          </Button>

          {draft?.ok && (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2 text-[12px]">
                <span className="text-muted-foreground">written to</span>
                <span className="font-mono text-foreground">{draft.document_path}</span>
                {draft.grounded_in_letter && (
                  <span className="rounded border border-success/40 bg-success/10 px-1.5 py-0.5 text-[11px] text-success">
                    grounded in the customer's letter
                  </span>
                )}
              </div>
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded border border-border bg-background/60 p-2 text-[11px] leading-relaxed text-foreground/85">
                {draft.preview}
              </pre>
              <Button size="sm" onClick={proposeDispatch} disabled={busy !== null}>
                {busy === "propose" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : null}
                Propose dispatch for approval
              </Button>
              {verdict && (
                <div className="space-y-1 pt-1">
                  <div className="text-[12px] text-muted-foreground">
                    Action #{verdict.id} staged — decide it on the Approvals tab.
                  </div>
                  <GuardrailVerdict guardrail={verdict.guardrail} />
                </div>
              )}
              {outbound.length > 0 && (
                <div className="space-y-1 pt-1">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Drafts the agent has produced
                  </div>
                  {outbound.slice(0, 10).map((d) => (
                    <div key={d.path} className="flex justify-between gap-2 text-[12px]">
                      <span className="font-mono text-foreground">{d.name}</span>
                      <span className="tabular-nums text-muted-foreground">{d.size} bytes</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
