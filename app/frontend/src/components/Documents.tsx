/** The volumes lane: the customer's own words next to the structured record, and a drafted reply.
 *
 *  Why this tab earns its place: a complaint row says `severity = 'Critical'`. The letter says the
 *  agent came at 9:15 pm and shouted the borrower's name so the neighbours could hear. The reply the
 *  agent drafts is grounded in the second, which is why it reads like an answer rather than a template.
 */
import { useEffect, useState } from "react";
import { Button, Card, CardContent } from "@databricks/appkit-ui/react";
import { FileSearch, FileText, Loader2, PenLine } from "lucide-react";
import { api, SearchResult, Draft, Evidence } from "../api";
import { ErrorText, SectionTitle, SyntheticBadge } from "./kit";
import { GuardrailVerdict } from "./Guardrails";
import type { Guardrail } from "../api";

// Complaints that have a letter in the volume. The first four are the Solapur microfinance
// recovery-conduct cases that corroborate the delinquency story in the structured tables.
const WITH_LETTERS = [
  "CM0009530",
  "CM0007800",
  "CM0007205",
  "CM0008238",
  "CM0008801",
  "CM0009377",
];

export function Documents({ onActed }: { onActed: () => void }) {
  // Semantic search over 713 letters. It earns its place because the thing a conduct committee wants to
  // ask — "which borrowers said the agent came after dark and told their neighbours" — is a phrasing, not
  // a column, and no amount of SQL over `complaint_documents` will find it.
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchErr, setSearchErr] = useState<string | null>(null);

  const runSearch = async (text: string) => {
    if (text.trim().length < 3) return;
    setSearching(true);
    setSearchErr(null);
    try {
      setHits(await api.search(text));
    } catch (e) {
      setSearchErr(String((e as Error).message || e));
    } finally {
      setSearching(false);
    }
  };

  const [cid, setCid] = useState("CM0009245");   // the LN001135 borrower's open conduct grievance
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [outbound, setOutbound] = useState<{ name: string; path: string; size: number }[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<{ id: number; guardrail: Guardrail } | null>(null);

  useEffect(() => {
    api.outbound().then((r) => setOutbound(r.documents)).catch(() => setOutbound([]));
  }, [draft]);

  async function load() {
    setBusy("load");
    setError(null);
    setDraft(null);
    setVerdict(null);
    try {
      setEvidence(await api.evidence(cid.trim().toUpperCase()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function makeDraft() {
    setBusy("draft");
    setError(null);
    try {
      setDraft(await api.draft(cid.trim().toUpperCase()));
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

  const rec = evidence?.record;

  return (
    <div className="space-y-4">
      <Card className="border-border">
        <CardContent className="space-y-3 p-4">
          {/* Semantic search first: this is the question SQL cannot answer. */}
          <div className="mb-5 rounded-lg border border-border bg-card p-4">
            <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
              <SectionTitle hint="Vector Search over 713 letters. The index is queried as the application's service principal and never granted to end users; every record it finds is then re-read under YOUR entitlements. Retrieval locates the letter, governance still decides whether you may read it.">
                Search what borrowers actually said
              </SectionTitle>
              <SyntheticBadge />
            </div>
            <div className="flex flex-wrap gap-2">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && runSearch(q)}
                placeholder="e.g. the agent told the women in my self-help group how much I owe"
                className="min-w-[22rem] flex-1 rounded border border-border bg-background px-3 py-1.5 text-xs text-foreground"
              />
              <Button size="sm" onClick={() => runSearch(q)} disabled={searching || q.trim().length < 3}>
                {searching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileSearch className="h-3.5 w-3.5" />}
                Search
              </Button>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {[
                "agent came after dark and shouted my name outside my house",
                "they told the women in my self-help group what I owe",
                "insurance was added to my loan without my consent",
                "nobody would show me an identity card",
              ].map((ex) => (
                <button
                  key={ex}
                  onClick={() => { setQ(ex); runSearch(ex); }}
                  className="rounded border border-border px-2 py-0.5 text-[10px] text-muted-foreground hover:bg-secondary"
                >
                  {ex.length > 46 ? ex.slice(0, 46) + "…" : ex}
                </button>
              ))}
            </div>

            {searchErr && <div className="mt-3"><ErrorText>{searchErr}</ErrorText></div>}

            {hits && !hits.ok && (
              <p className="mt-3 text-[11px] leading-relaxed text-warning">{hits.note}</p>
            )}

            {hits?.ok && (
              <>
                <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">{hits.note}</p>
                <div className="mt-2 space-y-2">
                  {hits.hits.map((h) => (
                    <div
                      key={h.complaint_id ?? h.snippet.slice(0, 20)}
                      className={
                        "rounded border px-3 py-2 " +
                        (h.outside_your_scope
                          ? "border-warning/40 bg-warning/10"
                          : "border-border bg-background")
                      }
                    >
                      <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                        <span className="font-semibold text-foreground">{h.complaint_id ?? "policy document"}</span>
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
                            onClick={() => { setCid(h.complaint_id as string); }}
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
                        <p className="mt-1 text-[10px] font-semibold text-warning">
                          Outside your entitlement — the letter exists and matched, but the record is not
                          yours to read. This is not "no such complaint".
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          <SectionTitle hint="Letters, internal compliance notes and agency contracts live in a Unity Catalog volume, parsed into a Delta table in the same schema — so the row filters and column masks that govern the tables govern the documents too, rather than sitting in a separate store with weaker controls.">
            Unstructured evidence
          </SectionTitle>
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={cid}
              onChange={(e) => setCid(e.target.value)}
              placeholder="CM0009530"
              className="w-40 rounded border border-border bg-background px-2 py-1 font-mono text-xs text-foreground"
            />
            <Button size="sm" onClick={load} disabled={busy !== null}>
              {busy === "load" ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <FileSearch className="mr-1.5 h-3.5 w-3.5" />
              )}
              Open the file
            </Button>
            <div className="flex flex-wrap gap-1">
              {WITH_LETTERS.map((c) => (
                <button
                  key={c}
                  onClick={() => setCid(c)}
                  className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${
                    c === cid
                      ? "border-primary/50 bg-primary/10 text-primary"
                      : "border-border text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {error && <ErrorText>{error}</ErrorText>}

      {evidence && !evidence.found && (
        <Card className="border-warning/40">
          <CardContent className="p-4 text-xs leading-relaxed text-warning">{evidence.note}</CardContent>
        </Card>
      )}

      {rec && (
        <div className="grid gap-3 lg:grid-cols-2">
          <Card className="border-border">
            <CardContent className="space-y-2 p-4">
              <SectionTitle>What our systems recorded</SectionTitle>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
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
              <p className="pt-1 text-[10px] leading-relaxed text-muted-foreground">
                The customer id is pseudonymised for you unless you are cleared to read raw
                identifiers. It is a stable token, so joins still work.
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
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded border border-border bg-background/60 p-2 text-[10px] leading-relaxed text-foreground/85">
                  {rec.document_text}
                </pre>
              ) : (
                <p className="text-xs text-muted-foreground">
                  No letter on file for this complaint.
                </p>
              )}
              {rec.file_path && (
                <p className="font-mono text-[10px] text-muted-foreground">{rec.file_path}</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {rec && (
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
                <div className="flex flex-wrap items-center gap-2 text-[11px]">
                  <span className="text-muted-foreground">written to</span>
                  <span className="font-mono text-foreground">{draft.document_path}</span>
                  {draft.grounded_in_letter && (
                    <span className="rounded border border-success/40 bg-success/10 px-1.5 py-0.5 text-[10px] text-success">
                      grounded in the customer's letter
                    </span>
                  )}
                </div>
                <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded border border-border bg-background/60 p-2 text-[10px] leading-relaxed text-foreground/85">
                  {draft.preview}
                </pre>
                <Button size="sm" onClick={proposeDispatch} disabled={busy !== null}>
                  {busy === "propose" ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  ) : null}
                  Propose dispatch for approval
                </Button>
                {verdict && (
                  <div className="space-y-1 pt-1">
                    <div className="text-[11px] text-muted-foreground">
                      Action #{verdict.id} staged — decide it on the Approvals tab.
                    </div>
                    <GuardrailVerdict guardrail={verdict.guardrail} />
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {outbound.length > 0 && (
        <Card className="border-border">
          <CardContent className="space-y-1 p-4">
            <SectionTitle>Drafts the agent has produced</SectionTitle>
            {outbound.slice(0, 10).map((d) => (
              <div key={d.path} className="flex justify-between gap-2 text-[11px]">
                <span className="font-mono text-foreground">{d.name}</span>
                <span className="tabular-nums text-muted-foreground">{d.size} bytes</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
