/** Renders a guardrail verdict.
 *
 *  The design rule here: never present all checks as equally trustworthy. A check confirmed against
 *  Unity Catalog and a check taken from the model's own payload are different kinds of statement, and
 *  a panel that styles them identically quietly overstates how much of this is enforced. So the
 *  `verified_by` field drives a visible badge, and the header states the ratio outright.
 */
import { Check, X, Minus, Database, FileWarning, ShieldOff } from "lucide-react";
import type { Guardrail, GuardrailCheck } from "../api";

const RULE_LABEL: Record<string, string> = {
  kill_switch: "Kill switch",
  action_type_allowed: "Action type permitted",
  autonomy_level: "Autonomy ceiling",
  max_amount_inr: "Value cap (INR)",
  allowed_regions: "Regional scope",
  account_exists: "Account resolves on the book",
  rbi_conduct_hours: "RBI borrower-contact window",
  agent_certification: "Recovery agent conduct certification",
  grievance_hold: "Open-grievance hold",
  dpd_floor: "Minimum delinquency",
  contact_cap: "Daily contact cap",
  requires_approval: "Human approval",
  loan_account_resolvable: "Loan account supplied",
};

function VerifiedBadge({ verifiedBy }: { verifiedBy: string }) {
  if (verifiedBy.startsWith("unity_catalog:")) {
    const fn = verifiedBy.split(":")[1];
    if (fn === "UNAVAILABLE" || fn === "NOT_EVALUATED") {
      return (
        <span className="inline-flex items-center gap-1 rounded border border-destructive/40 bg-destructive/10 px-1.5 py-0.5 text-[10px] font-medium text-destructive">
          <ShieldOff className="h-3 w-3" />
          {fn === "UNAVAILABLE" ? "could not verify" : "not evaluated"}
        </span>
      );
    }
    return (
      <span
        className="inline-flex items-center gap-1 rounded border border-success/40 bg-success/10 px-1.5 py-0.5 text-[10px] font-medium text-success"
        title={`Verified by the Unity Catalog function ${fn}()`}
      >
        <Database className="h-3 w-3" />
        UC-verified
      </span>
    );
  }
  if (verifiedBy.startsWith("lakebase:")) {
    return (
      <span className="inline-flex items-center gap-1 rounded border border-primary/40 bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
        <Database className="h-3 w-3" />
        policy table
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1 rounded border border-warning/40 bg-warning/10 px-1.5 py-0.5 text-[10px] font-medium text-warning"
      title="Taken from the request payload — not independently confirmed against governed data"
    >
      <FileWarning className="h-3 w-3" />
      from request
    </span>
  );
}

function CheckRow({ check }: { check: GuardrailCheck }) {
  const icon = !check.applicable ? (
    <Minus className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
  ) : check.passed ? (
    <Check className="mt-0.5 h-4 w-4 shrink-0 text-success" />
  ) : (
    <X className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
  );
  return (
    <div className="flex gap-2 border-t border-border/50 py-2 first:border-t-0">
      {icon}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={
              check.applicable
                ? "text-xs font-semibold text-foreground"
                : "text-xs font-medium text-muted-foreground"
            }
          >
            {RULE_LABEL[check.rule] ?? check.rule}
          </span>
          {check.applicable && <VerifiedBadge verifiedBy={check.verified_by} />}
          {check.limit !== null && check.limit !== undefined && (
            <span className="text-[10px] text-muted-foreground">
              limit: {String(check.limit)}
            </span>
          )}
        </div>
        <div className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{check.detail}</div>
        {check.legal_basis && !check.passed && (
          <div className="mt-1 rounded border-l-2 border-warning/60 bg-warning/5 px-2 py-1 text-[11px] leading-relaxed text-warning/90">
            {check.legal_basis}
          </div>
        )}
      </div>
    </div>
  );
}

export function GuardrailVerdict({ guardrail }: { guardrail: Guardrail }) {
  const { passed, breaches, checks, verified_count, payload_count } = guardrail;
  return (
    <div className="rounded-lg border border-border bg-card">
      <div
        className={`flex flex-wrap items-center justify-between gap-2 rounded-t-lg border-b px-4 py-2.5 ${
          passed
            ? "border-success/30 bg-success/10"
            : "border-destructive/30 bg-destructive/10"
        }`}
      >
        <div className="flex items-center gap-2">
          {passed ? (
            <Check className="h-4 w-4 text-success" />
          ) : (
            <X className="h-4 w-4 text-destructive" />
          )}
          <span
            className={`text-sm font-semibold ${passed ? "text-success" : "text-destructive"}`}
          >
            {passed ? "All controls passed" : `Refused by ${breaches.length} control${breaches.length === 1 ? "" : "s"}`}
          </span>
        </div>
        {/* The honesty line. Stated plainly so nobody has to infer how much is really enforced. */}
        <span className="text-[11px] text-muted-foreground">
          {verified_count} verified against governed data
          {payload_count > 0 && `, ${payload_count} taken from the request`}
        </span>
      </div>

      {breaches.length > 0 && (
        <div className="border-b border-border bg-destructive/5 px-4 py-2">
          <ul className="space-y-1">
            {breaches.map((b, i) => (
              <li key={i} className="text-xs leading-relaxed text-destructive">
                • {b}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="px-4 py-1">
        {checks.map((c, i) => (
          <CheckRow key={`${c.rule}-${i}`} check={c} />
        ))}
      </div>
    </div>
  );
}
