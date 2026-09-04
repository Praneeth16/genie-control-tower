/** The governance panel — the evidence layer.
 *
 *  Everything on this tab is read from the platform rather than asserted by the app: row filters and
 *  masks from information_schema, Genie activity from system.access.audit, the conduct policies from
 *  the table the guardrail engine actually reads. That is the point — an AI CoE should be able to
 *  check these numbers without taking our word for anything.
 */
import { useEffect, useState } from "react";
import { Badge, Button, Card, CardContent } from "@databricks/appkit-ui/react";
import {
  AlertTriangle,
  Ban,
  Database,
  Eye,
  FileText,
  Gauge,
  Loader2,
  Play,
  ShieldCheck,
} from "lucide-react";
import { api, AuditFeed, Controls, Policies, Scope, Usage } from "../api";
import { ErrorText, fmtIST, SectionTitle, Stat } from "./kit";

export function Governance() {
  const [scope, setScope] = useState<Scope | null>(null);
  const [policies, setPolicies] = useState<Policies | null>(null);
  const [controls, setControls] = useState<Controls | null>(null);
  const [audit, setAudit] = useState<AuditFeed | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [flipping, setFlipping] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      api.scope(),
      api.policies(),
      api.controls(),
      api.audit(),
      api.usage(),
    ])
      .then(([s, p, c, a, u]) => {
        if (s.status === "fulfilled") setScope(s.value);
        if (p.status === "fulfilled") setPolicies(p.value);
        if (c.status === "fulfilled") setControls(c.value);
        if (a.status === "fulfilled") setAudit(a.value);
        if (u.status === "fulfilled") setUsage(u.value);
        const failed = [s, p, c, a, u].filter((r) => r.status === "rejected");
        if (failed.length) setError(`${failed.length} panel(s) failed to load`);
      })
      .finally(() => setLoading(false));
  }, [tick]);

  async function flip(enabled: boolean) {
    setFlipping(true);
    try {
      await api.killSwitch(
        enabled,
        enabled ? "resumed from the governance panel" : "stopped from the governance panel"
      );
      setTick(tick + 1);
    } finally {
      setFlipping(false);
    }
  }

  if (loading)
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> reading the catalog…
      </div>
    );

  const killOn = controls?.kill_switch.actions_enabled ?? true;
  const blinded = controls?.guardrail_visibility?.blinded === true;

  return (
    <div className="space-y-5">
      {error && <ErrorText>{error}</ErrorText>}

      {/* Kill switch + guardrail integrity */}
      <div className="grid gap-3 md:grid-cols-2">
        <Card className={killOn ? "border-border" : "border-destructive/50 bg-destructive/5"}>
          <CardContent className="space-y-2 p-4">
            <div className="flex items-center gap-2">
              <Ban className={`h-4 w-4 ${killOn ? "text-muted-foreground" : "text-destructive"}`} />
              <SectionTitle hint="Stopping the agents is a data change, not a redeploy. The executor re-reads this before every outbound call, so it stops actions that are already approved and waiting.">
                Kill switch
              </SectionTitle>
            </div>
            <div className="text-xs text-muted-foreground">{controls?.kill_switch.detail}</div>
            <Button
              size="sm"
              variant={killOn ? "outline" : "default"}
              onClick={() => flip(!killOn)}
              disabled={flipping}
            >
              {flipping ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : killOn ? (
                <Ban className="mr-1.5 h-3.5 w-3.5" />
              ) : (
                <Play className="mr-1.5 h-3.5 w-3.5" />
              )}
              {killOn ? "Stop all actions" : "Resume actions"}
            </Button>
          </CardContent>
        </Card>

        <Card className={blinded ? "border-destructive/50 bg-destructive/5" : "border-border"}>
          <CardContent className="space-y-2 p-4">
            <div className="flex items-center gap-2">
              {blinded ? (
                <AlertTriangle className="h-4 w-4 text-destructive" />
              ) : (
                <ShieldCheck className="h-4 w-4 text-success" />
              )}
              <SectionTitle hint="A control that cannot see the data it protects reports every action compliant. The app asserts its guardrail identity is unfiltered before it serves traffic.">
                Guardrail integrity
              </SectionTitle>
            </div>
            {blinded ? (
              <div className="text-xs leading-relaxed text-destructive">
                {String(controls?.guardrail_visibility?.error)}
              </div>
            ) : (
              <div className="space-y-1">
                <div className="text-xs text-success">
                  The guardrail identity sees the whole book — it is not being row-filtered.
                </div>
                <div className="grid grid-cols-2 gap-x-3 text-[12px] tabular-nums text-muted-foreground">
                  {Object.entries(
                    (controls?.guardrail_visibility?.visible ?? {}) as Record<string, number>
                  ).map(([t, n]) => (
                    <div key={t} className="flex justify-between">
                      <span>{t}</span>
                      <span>{n.toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* What THIS user can see */}
      {scope && (
        <Card className="border-border">
          <CardContent className="space-y-3 p-4">
            <div className="flex items-center gap-2">
              <Eye className="h-4 w-4 text-primary" />
              <SectionTitle hint="Read on behalf of the signed-in user, so these are that person's own entitlements. Sign in as someone else and every number below changes.">
                What you are entitled to see
              </SectionTitle>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-[12px]">
              <span className="font-mono text-foreground">{scope.identity}</span>
              {Object.entries(scope.group_memberships)
                .filter(([, v]) => v)
                .map(([g]) => (
                  <Badge key={g} variant="outline" className="text-[11px]">
                    {g}
                  </Badge>
                ))}
              {scope.masked_customer_id_example && (
                <span className="ml-auto text-muted-foreground">
                  customer ids appear to you as{" "}
                  <span className="font-mono text-foreground">
                    {scope.masked_customer_id_example}
                  </span>
                </span>
              )}
            </div>
            <p className="text-[12px] leading-relaxed text-muted-foreground">{scope.note}</p>
            <div className="space-y-1">
              {scope.tables.map((t) => (
                <div key={t.table} className="flex items-center gap-2">
                  <span className="w-44 shrink-0 text-[12px] text-muted-foreground">{t.table}</span>
                  <div className="h-2.5 flex-1 overflow-hidden rounded-sm bg-secondary">
                    <div
                      className={`h-full rounded-sm ${t.pct >= 100 ? "bg-success/60" : "bg-warning/70"}`}
                      style={{ width: `${Math.min(100, t.pct)}%` }}
                    />
                  </div>
                  <span className="w-32 shrink-0 text-right text-[11px] tabular-nums text-muted-foreground">
                    {t.visible.toLocaleString()} / {t.total.toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Enforced policies, straight from information_schema */}
      {policies && (
        <Card className="border-border">
          <CardContent className="space-y-3 p-4">
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-primary" />
              <SectionTitle hint="Read from information_schema — what is actually attached in Unity Catalog, not what our SQL files claim.">
                Enforced in Unity Catalog
              </SectionTitle>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              <Stat label="row filters" value={policies.summary.row_filters} />
              <Stat label="column masks" value={policies.summary.column_masks} />
              <Stat label="tagged columns" value={policies.summary.tagged_columns} />
              <Stat label="tagged tables" value={policies.summary.tagged_tables} />
              <Stat label="UC functions" value={policies.summary.uc_functions} />
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Column masks
                </div>
                <div className="space-y-0.5">
                  {policies.column_masks.map((m, i) => (
                    <div key={i} className="text-[12px] text-muted-foreground">
                      <span className="font-mono text-foreground">
                        {m.table_name}.{m.column_name}
                      </span>{" "}
                      → {m.mask_name}
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Row filters
                </div>
                <div className="space-y-0.5">
                  {policies.row_filters.map((f, i) => (
                    <div key={i} className="text-[12px] text-muted-foreground">
                      <span className="font-mono text-foreground">{f.table_name}</span> →{" "}
                      {f.filter_name}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Conduct policies with their legal basis */}
      {controls && (
        <Card className="border-border">
          <CardContent className="space-y-2 p-4">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-primary" />
              <SectionTitle hint="The controls the guardrail engine reads, with the regulation each implements. The control is ours; the citation must be confirmed by the bank's compliance function.">
                Conduct policies
              </SectionTitle>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead className="bg-secondary/50">
                  <tr>
                    {["action", "domain", "approver", "max L", "cap INR", "conduct controls"].map(
                      (h) => (
                        <th key={h} className="px-2 py-1 text-left font-semibold text-muted-foreground">
                          {h}
                        </th>
                      )
                    )}
                  </tr>
                </thead>
                <tbody>
                  {controls.policies.map((p, i) => {
                    const flags = [
                      p.rbi_conduct_hours && "contact hours",
                      p.requires_agent_certification && "agent certified",
                      p.blocked_by_open_grievance && "grievance hold",
                      p.min_dpd_days && `${p.min_dpd_days}+ DPD`,
                      p.max_contacts_per_day && `${p.max_contacts_per_day}/day`,
                    ].filter(Boolean);
                    return (
                      <tr key={i} className="border-t border-border/60 align-top">
                        <td className="px-2 py-1 font-mono text-foreground">
                          {String(p.action_type)}
                        </td>
                        <td className="px-2 py-1 text-muted-foreground">{String(p.domain)}</td>
                        <td className="px-2 py-1 text-muted-foreground">
                          {p.approver_role ? String(p.approver_role) : "— none"}
                        </td>
                        <td className="px-2 py-1 tabular-nums text-muted-foreground">
                          L{String(p.max_autonomy_level)}
                        </td>
                        <td className="px-2 py-1 tabular-nums text-muted-foreground">
                          {p.max_amount_inr
                            ? Number(p.max_amount_inr).toLocaleString("en-IN")
                            : "—"}
                        </td>
                        <td className="px-2 py-1 text-muted-foreground">
                          {flags.length ? flags.join(", ") : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Usage and cost */}
      {usage && (
        <Card className="border-border">
          <CardContent className="space-y-3 p-4">
            <div className="flex items-center gap-2">
              <Gauge className="h-4 w-4 text-primary" />
              <SectionTitle hint="Per-question attribution from this app's own session log. Billing aggregates by warehouse, which is not the number a budget owner needs.">
                Usage
              </SectionTitle>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="questions" value={String(usage.turns.turns ?? 0)} />
              <Stat label="people" value={String(usage.turns.users ?? 0)} />
              <Stat
                label="avg latency"
                value={`${((Number(usage.turns.avg_latency_ms) || 0) / 1000).toFixed(1)}s`}
              />
              <Stat
                label="p95 latency"
                value={`${((Number(usage.turns.p95_latency_ms) || 0) / 1000).toFixed(1)}s`}
              />
            </div>
            <p className="text-[12px] leading-relaxed text-muted-foreground">{usage.note}</p>
          </CardContent>
        </Card>
      )}

      {/* Platform audit */}
      {audit && (
        <Card className="border-border">
          <CardContent className="space-y-2 p-4">
            <SectionTitle hint="system.access.audit is the platform's own record, written whether or not this app is running. It lags by a few minutes.">
              Genie activity from the platform audit log
            </SectionTitle>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(audit.by_action).map(([a, n]) => (
                <Badge key={a} variant="outline" className="text-[11px]">
                  {a} · {n}
                </Badge>
              ))}
            </div>
            <div className="max-h-64 overflow-auto rounded border border-border">
              <table className="w-full text-[11px]">
                <thead className="sticky top-0 bg-secondary/80">
                  <tr>
                    {["time (IST)", "user", "action", "space", "status"].map((h) => (
                      <th key={h} className="px-2 py-1 text-left font-semibold text-muted-foreground">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {audit.events.map((e, i) => (
                    <tr key={i} className="border-t border-border/50">
                      <td className="whitespace-nowrap px-2 py-0.5 tabular-nums text-muted-foreground">
                        {fmtIST(e.event_time)}
                      </td>
                      <td className="px-2 py-0.5 text-muted-foreground">{e.user_email}</td>
                      <td className="px-2 py-0.5 text-foreground">{e.action_name}</td>
                      <td className="px-2 py-0.5 font-mono text-muted-foreground">
                        {e.space_id ? String(e.space_id).slice(0, 12) : "—"}
                      </td>
                      {/* A 429 here is the workspace Genie quota being hit — visible in the platform's
                          own audit log, not just in our app's error handling. */}
                      <td
                        className={`px-2 py-0.5 tabular-nums ${
                          String(e.status_code) === "429" ? "text-warning" : "text-muted-foreground"
                        }`}
                      >
                        {e.status_code}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
