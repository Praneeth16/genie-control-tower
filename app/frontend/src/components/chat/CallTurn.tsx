/** One live-call turn: the RBI conduct verdict, then the account facts behind it.
 *
 *  Read the note at the top of backend/voice.py for why this is assist and not a customer-facing bot.
 *  The short version: the Databricks voice reference stack measures 30-40s end to end today, which is
 *  fatal to self-service and fine for assist, and putting a generative voice in front of a retail
 *  borrower is an RBI conduct exposure a bank should not take on in a first project.
 *
 *  Conduct comes first and is unmissable. On a live call it is the only thing that changes what the
 *  officer is allowed to say next, so it outranks the account detail below it.
 */
import { Card, CardContent } from "@databricks/appkit-ui/react";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { ShieldCheck } from "lucide-react";
import type { VoiceAssist } from "../../api";
import { ErrorText, RowTable, SectionTitle, Stat } from "../kit";
import { RULE_LABEL } from "../Guardrails";

export function CallTurn({
  assist,
  live,
  pending,
  error,
}: {
  assist: VoiceAssist | null;
  live: boolean;
  pending: boolean;
  error: string | null;
}) {
  if (!assist) {
    // Three distinct states, and the third one is the point. "Resolving…" used to be shown for ALL of
    // them, so a call that ended with nothing said, a refused microphone, or a failed lookup all left a
    // spinner that could never resolve — the UI claiming work was in progress when none was.
    const message = pending
      ? "Resolving the call against governed tables…"
      : live
        ? "Listening — the conduct verdict appears as soon as an account is named."
        : error
          ? "The lookup failed, so no conduct verdict was reached on this call."
          : "This call ended before an account was named, so nothing was resolved and no conduct verdict applies.";
    return (
      <Card className={error ? "border-destructive/40" : "border-border"}>
        <CardContent className="space-y-2 p-4">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {(pending || live) && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {message}
          </div>
          {error && <ErrorText>{error}</ErrorText>}
        </CardContent>
      </Card>
    );
  }

  const conductFail = (assist.conduct || []).filter((c) => !c.passed);

  return (
    <div className="space-y-3">
      <Card className="border-border">
        <CardContent className="space-y-3 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <SectionTitle hint="The same Unity Catalog controls the action plane enforces, evaluated against this call's clock. Verified as the service principal, never on your behalf — a check you could blind with your own row filters would not be a check.">
              Conduct
            </SectionTitle>
            {live && (
              <span className="mb-3 inline-flex items-center gap-1 rounded border border-destructive/40 bg-destructive/10 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-destructive">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-destructive" />
                live
              </span>
            )}
            {pending && <Loader2 className="mb-3 h-3 w-3 animate-spin text-muted-foreground" />}
          </div>

          {/* A verdict is only meaningful next to the words it was computed from. Without this, a refresh
              that failed or was superseded leaves a stale banner that looks current. */}
          {error && <ErrorText>{error}</ErrorText>}

          <div className="space-y-2">
            {(assist.conduct || []).map((c) => (
              <div
                key={c.rule}
                className={
                  "flex items-start gap-2 rounded border px-3 py-2 text-xs " +
                  (c.passed
                    ? "border-success/30 bg-success/10 text-foreground"
                    : "border-destructive/40 bg-destructive/10 text-foreground")
                }
              >
                {c.passed ? (
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
                ) : (
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
                )}
                <div>
                  <div className="font-semibold">{RULE_LABEL[c.rule] ?? c.rule}</div>
                  <div className="text-muted-foreground">{c.detail}</div>
                  <div className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                    <ShieldCheck className="h-3 w-3" />
                    verified by {c.verified_by}
                  </div>
                </div>
              </div>
            ))}
          </div>
          {conductFail.length > 0 && (
            <p className="text-[12px] font-semibold text-destructive">
              {conductFail.length} control(s) failed — do not proceed with recovery on this call.
            </p>
          )}
        </CardContent>
      </Card>

      <Card className="border-border">
        <CardContent className="space-y-3 p-4">
          <SectionTitle hint="Heard in the call and resolved against governed tables.">
            What the call is about
          </SectionTitle>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Loan account" value={assist.entities.loan_account_id || "—"} />
            <Stat label="Complaint" value={assist.entities.complaint_id || "—"} />
            <Stat
              label="Customer"
              value={assist.customer_id || "—"}
              sub="pseudonymised by column mask"
            />
            <Stat
              label="Open grievances"
              value={String(assist.grievance?.open_complaints ?? "—")}
              sub={assist.grievance?.open_ground ? String(assist.grievance.open_ground) : undefined}
            />
          </div>

          {assist.not_visible && (
            <p className="text-[12px] leading-relaxed text-warning">
              An identifier was recognised but no record came back. Under on-behalf-of-user auth that
              means it is <strong>outside your entitlement</strong> — it does not mean the record does
              not exist. Escalate rather than telling the customer there is no such account.
            </p>
          )}

          {assist.loan && (
            <div>
              <SectionTitle>Account</SectionTitle>
              <RowTable columns={[]} rows={[assist.loan]} />
            </div>
          )}
          {assist.contact && (
            <div>
              <SectionTitle hint="Prior contact on this account over the whole book, including any out-of-hours attempts already on record.">
                Contact history
              </SectionTitle>
              {Number(assist.contact.contact_attempts ?? 0) > 0 ? (
                <RowTable columns={[]} rows={[assist.contact]} />
              ) : (
                <div className="text-xs text-muted-foreground">
                  No contact attempts are recorded against this account.
                </div>
              )}
            </div>
          )}
          {assist.complaint && (
            <div>
              <SectionTitle>Referenced complaint</SectionTitle>
              <RowTable columns={[]} rows={[assist.complaint]} />
              <p className="mt-1 text-[12px] text-muted-foreground">
                Received {String(assist.complaint.received_date ?? "—")} (date only — no time is
                recorded on a complaint, so none is shown)
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
