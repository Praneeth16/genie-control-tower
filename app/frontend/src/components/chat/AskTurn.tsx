/** One supervisor turn: routing -> per-domain Genie answers -> the fused answer -> a proposable action.
 *
 *  Two things are deliberately not hidden. The SQL each Genie Agent wrote is one click away, because an
 *  analyst who cannot see the query cannot sign off on the number. And the per-leg timing is shown,
 *  because these answers take 15-45s and pretending otherwise sets the wrong expectation for anyone
 *  planning to put this in front of a branch.
 *
 *  The action proposal keeps its state per turn rather than per screen, so an earlier turn's staged
 *  action and verdict stay readable after the next question is asked.
 */
import { useState } from "react";
import { Badge, Button, Card, CardContent, Collapsible, CollapsibleContent, CollapsibleTrigger } from "@databricks/appkit-ui/react";
import {
  ChevronDown,
  Clock,
  Code2,
  GitBranch,
  Loader2,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { api, AskResult, Guardrail } from "../../api";
import { DomainBadge, DOMAIN_LABEL, ErrorText, fmtIST, RowTable, SectionTitle, ViaBadge } from "../kit";
import { GuardrailVerdict } from "../Guardrails";

function LegCard({ leg }: { leg: AskResult["legs"][number] }) {
  return (
    <Card className="border-border">
      <CardContent className="space-y-2 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <DomainBadge domain={leg.domain} />
          <span className="text-xs font-medium text-foreground">
            {DOMAIN_LABEL[leg.domain] ?? leg.domain}
          </span>
          <ViaBadge via={leg.via} />
          <span className="ml-auto inline-flex items-center gap-1 text-[12px] tabular-nums text-muted-foreground">
            <Clock className="h-3 w-3" />
            {(leg.elapsed_ms / 1000).toFixed(1)}s · {leg.row_count} rows
          </span>
        </div>

        {leg.error && (
          <div className="rounded border border-warning/40 bg-warning/10 px-2 py-1.5 text-[12px] leading-relaxed text-warning">
            {leg.error}
          </div>
        )}

        {leg.narrative_defect && (
          <div className="rounded border border-warning/40 bg-warning/10 px-2 py-1.5 text-[12px] leading-relaxed text-warning">
            {leg.narrative_defect}
          </div>
        )}
        {leg.description && (
          <p className="text-xs leading-relaxed text-foreground/80">{leg.description}</p>
        )}

        {leg.sql && (
          <Collapsible>
            <CollapsibleTrigger className="flex items-center gap-1 text-[12px] font-medium text-primary hover:underline">
              <Code2 className="h-3 w-3" />
              Show the SQL Genie wrote
              <ChevronDown className="h-3 w-3" />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <pre className="mt-2 max-h-64 overflow-auto rounded border border-border bg-background/60 p-2 text-[11px] leading-relaxed text-foreground/80">
                {leg.sql}
              </pre>
              {leg.rows.length > 0 && (
                <div className="mt-2">
                  <RowTable columns={leg.columns} rows={leg.rows} max={8} />
                </div>
              )}
            </CollapsibleContent>
          </Collapsible>
        )}
      </CardContent>
    </Card>
  );
}

/** Per-leg timing as a bar chart. Makes the parallelism visible: three legs finishing together is the
 *  reason a three-domain question costs one leg of wall clock instead of three. */
function TraceWaterfall({ result }: { result: AskResult }) {
  const max = Math.max(result.latency_ms, ...result.legs.map((l) => l.elapsed_ms), 1);
  return (
    <div className="space-y-1.5">
      {result.legs.map((l) => (
        <div key={l.domain} className="flex items-center gap-2">
          <span className="w-24 shrink-0 text-[11px] font-semibold uppercase text-muted-foreground">
            {l.domain}
          </span>
          <div className="h-3 flex-1 overflow-hidden rounded-sm bg-secondary">
            <div
              className="h-full rounded-sm bg-primary/70"
              style={{ width: `${Math.max(2, (l.elapsed_ms / max) * 100)}%` }}
            />
          </div>
          <span className="w-14 shrink-0 text-right text-[11px] tabular-nums text-muted-foreground">
            {(l.elapsed_ms / 1000).toFixed(1)}s
          </span>
        </div>
      ))}
      <div className="flex items-center gap-2 border-t border-border/60 pt-1.5">
        <span className="w-24 shrink-0 text-[11px] font-semibold uppercase text-foreground">
          whole turn
        </span>
        <div className="h-3 flex-1 overflow-hidden rounded-sm bg-secondary">
          <div className="h-full w-full rounded-sm bg-foreground/30" />
        </div>
        <span className="w-14 shrink-0 text-right text-[11px] font-semibold tabular-nums text-foreground">
          {(result.latency_ms / 1000).toFixed(1)}s
        </span>
      </div>
      <p className="pt-1 text-[11px] leading-relaxed text-muted-foreground">
        Legs run in parallel, so the turn costs roughly the slowest domain plus the router and fuser
        calls — not the sum of the domains.
      </p>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 font-mono text-xs text-foreground">{value}</div>
    </div>
  );
}

/** datetime-local wants a local-time string with no zone; toISOString would shift it. */
function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(
    d.getMinutes()
  )}`;
}

/** A compliant slot by default so the happy path works, while leaving it editable — moving it to an
 *  evening is how the RBI contact-window control gets demonstrated.
 *
 *  15:00 **IST**, expressed in the viewer's local time. `datetime-local` is interpreted as LOCAL time, so
 *  writing 15:00 into it schedules 15:00 in whatever zone the presenting laptop is in — and 15:00 PDT is
 *  03:30 IST, which `rbi_conduct_hours` correctly refuses. The "compliant by default" path would then be
 *  refused before anyone touched the control, which is the opposite of the point. Everywhere else in this
 *  app pins IST explicitly rather than trusting the viewer's clock (see fmtIST in kit.tsx); this was the
 *  one place that did not.
 */
function defaultSchedule(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const g = (t: string) => parts.find((p) => p.type === t)?.value ?? "01";
  // IST is UTC+5:30 and has no daylight saving, so 15:00 IST is 09:30 UTC on the same IST date.
  return toLocalInput(new Date(`${g("year")}-${g("month")}-${g("day")}T09:30:00Z`));
}

export function AskTurn({ result, onActed }: { result: AskResult; onActed: () => void }) {
  const [scheduledAt, setScheduledAt] = useState(defaultSchedule);
  const [proposing, setProposing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rated, setRated] = useState<number | null>(null);
  const [verdict, setVerdict] = useState<{ id: number; guardrail: Guardrail; role: string | null } | null>(
    null
  );

  async function propose() {
    if (!result.action_draft || proposing) return;
    setProposing(true);
    setError(null);
    try {
      const d = result.action_draft;
      const r = await api.act({
        action_type: d.action_type,
        subject: d.subject,
        payload: d.payload,
        region: d.region,
        level: d.level,
        scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
        session_uuid: result.session_uuid,
        trace_id: result.trace_id,
      });
      setVerdict({ id: r.action.id, guardrail: r.guardrail, role: r.approver_role });
      onActed();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setProposing(false);
    }
  }

  return (
    <div className="space-y-3">
      {/* Routing — the answer to "why did it look there?" */}
      <Card className="border-border">
        <CardContent className="space-y-2 p-4">
          <div className="flex items-center gap-2">
            <GitBranch className="h-3.5 w-3.5 text-primary" />
            <SectionTitle>Routing decision</SectionTitle>
          </div>
          {result.router_fallback && (
            <div className="rounded border border-warning/40 bg-warning/10 px-2 py-1 text-[12px] text-warning">
              The router did not return a usable decision, so a single domain was consulted rather than
              guessing across all three.
            </div>
          )}
          {result.routing.map((r) => (
            <div key={r.domain} className="flex gap-2">
              <DomainBadge domain={r.domain} />
              <span className="text-xs leading-relaxed text-muted-foreground">{r.reason}</span>
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="grid gap-3 lg:grid-cols-2">
        {result.legs.map((l) => (
          <LegCard key={l.domain} leg={l} />
        ))}
      </div>

      {/* The fused answer */}
      <Card className="border-primary/30 bg-primary/5">
        <CardContent className="space-y-3 p-4">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <SectionTitle>Supervisor answer</SectionTitle>
            <Badge variant="outline" className="ml-auto text-[11px]">
              {(result.latency_ms / 1000).toFixed(1)}s
            </Badge>
          </div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{result.answer}</p>
          {result.recommended_action && (
            <div className="rounded border-l-2 border-primary/60 bg-background/40 px-3 py-2">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-primary">
                Recommended action
              </div>
              <p className="mt-0.5 text-xs leading-relaxed text-foreground/90">
                {result.recommended_action}
              </p>
            </div>
          )}
          <div className="flex items-center gap-2 pt-1">
            <Button
              size="sm"
              variant={rated === 1 ? "default" : "outline"}
              onClick={async () => {
                // Caught, not floated: a failed write used to leave the thumb un-highlighted with no
                // explanation and an unhandled rejection that surfaced in QA as an unrelated pageerror.
                try {
                  await api.feedback(result.session_uuid, 1);
                  setRated(1);
                } catch (e) {
                  setError(e instanceof Error ? e.message : String(e));
                }
              }}
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="sm"
              variant={rated === -1 ? "default" : "outline"}
              onClick={async () => {
                try {
                  await api.feedback(result.session_uuid, -1);
                  setRated(-1);
                } catch (e) {
                  setError(e instanceof Error ? e.message : String(e));
                }
              }}
            >
              <ThumbsDown className="h-3.5 w-3.5" />
            </Button>
            {result.trace_id && (
              <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                trace {result.trace_id.slice(0, 20)}
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Timing */}
      <Card className="border-border">
        <CardContent className="space-y-2 p-4">
          <SectionTitle>Where the time went</SectionTitle>
          <TraceWaterfall result={result} />
        </CardContent>
      </Card>

      {error && <ErrorText>{error}</ErrorText>}

      {/* The action */}
      {result.action_draft ? (
        <Card className="border-warning/30">
          <CardContent className="space-y-3 p-4">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-warning" />
              <SectionTitle hint="A proposal, not a decision. It is checked against the bank's controls and needs a named human approver before anything reaches a downstream system.">
                Proposed action
              </SectionTitle>
            </div>
            <div className="grid gap-2 text-xs sm:grid-cols-2">
              <Field label="Action" value={result.action_draft.action_type} />
              <Field label="Subject" value={result.action_draft.subject} />
              <Field label="Region" value={result.action_draft.region ?? "—"} />
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Scheduled for
                </div>
                <input
                  type="datetime-local"
                  value={scheduledAt}
                  onChange={(e) => setScheduledAt(e.target.value)}
                  className="mt-0.5 w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground"
                />
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  {/* The control evaluates this instant in IST. Showing that conversion is not decoration:
                      the input reads in the presenter's own zone, so without it a refusal for 03:30 IST
                      looks like a bug when the box plainly says 15:00. */}
                  {scheduledAt && (
                    <span className="text-foreground">
                      {fmtIST(new Date(scheduledAt).toISOString(), false)} ·{" "}
                    </span>
                  )}
                  {/* CONDITIONAL, because the borrower-contact window is attached to
                      schedule_field_visit alone — a coaching case at 21:45 is not a borrower contact, so
                      the control does not apply. This line promised a refusal for every action type, so a
                      presenter could set an evening time, watch it pass, and have no idea why. */}
                  {result.action_draft.action_type === "schedule_field_visit"
                    ? "Try an evening time to see the RBI contact-window control refuse it."
                    : `The RBI borrower-contact window governs schedule_field_visit only, so an evening time is not refused for ${result.action_draft.action_type} — it is not a borrower contact.`}
                </div>
              </div>
            </div>
            <pre className="max-h-32 overflow-auto rounded border border-border bg-background/60 p-2 text-[11px] text-foreground/80">
              {JSON.stringify(result.action_draft.payload, null, 2)}
            </pre>
            <Button size="sm" onClick={propose} disabled={proposing}>
              {proposing ? (
                <>
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> Checking controls…
                </>
              ) : (
                "Propose and check the controls"
              )}
            </Button>

            {verdict && (
              <div className="space-y-2 pt-1">
                <div className="text-[12px] text-muted-foreground">
                  Action #{verdict.id} staged
                  {verdict.role && ` · requires sign-off by ${verdict.role}`} · decide it on the
                  Approvals tab
                </div>
                <GuardrailVerdict guardrail={verdict.guardrail} />
              </div>
            )}
          </CardContent>
        </Card>
      ) : (
        <Card className="border-border">
          <CardContent className="p-4 text-xs text-muted-foreground">
            No action proposed for this question — it was answered as analysis only.
          </CardContent>
        </Card>
      )}
    </div>
  );
}
