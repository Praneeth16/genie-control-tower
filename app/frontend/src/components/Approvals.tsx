/** The approval queue — where a human decides, and where the record of that decision lives.
 *
 *  The queue shows the guardrail verdict BEFORE the approve button, not after. An approval screen that
 *  makes you click through to find out what the controls said is training people to rubber-stamp.
 */
import { useEffect, useState } from "react";
import { Badge, Button, Card, CardContent } from "@databricks/appkit-ui/react";
import { Loader2, PlayCircle, RefreshCw, ShieldX, ThumbsUp, XCircle } from "lucide-react";
import { Action, ActionEvent, api, Guardrail } from "../api";
import { ErrorText, fmtIST, SectionTitle, StatusBadge } from "./kit";
import { GuardrailVerdict } from "./Guardrails";

const OPEN = new Set(["proposed", "approved", "escalated"]);

function Timeline({ events }: { events: ActionEvent[] }) {
  return (
    <ol className="space-y-1.5">
      {events.map((e) => {
        const d = (e.detail ?? {}) as Record<string, unknown>;
        const note =
          (d.reason as string) ||
          (Array.isArray(d.breaches) && d.breaches.length
            ? (d.breaches as string[]).join("; ")
            : "") ||
          (d.external_ref as string) ||
          (d.basis as string) ||
          (d.verified_count !== undefined
            ? `${d.verified_count} controls verified against governed data`
            : "");
        return (
          <li key={e.id} className="flex gap-2 text-[11px]">
            <span className="w-36 shrink-0 tabular-nums text-muted-foreground">
              {fmtIST(e.ts)}
            </span>
            <span
              className={`w-32 shrink-0 font-semibold ${
                e.event.includes("refused") || e.event.includes("fail") || e.event === "escalated"
                  ? "text-destructive"
                  : e.event === "executed"
                    ? "text-success"
                    : "text-foreground"
              }`}
            >
              {e.event}
            </span>
            <span className="w-56 shrink-0 truncate text-muted-foreground">{e.actor}</span>
            <span className="min-w-0 flex-1 text-muted-foreground">{note}</span>
          </li>
        );
      })}
    </ol>
  );
}

function ActionRow({ action, onChanged }: { action: Action; onChanged: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [guardrail, setGuardrail] = useState<Guardrail | null>(null);
  const [events, setEvents] = useState<ActionEvent[]>(action.events ?? []);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const r = await api.action(action.id);
    setGuardrail(r.guardrail);
    setEvents(r.action.events ?? []);
  }

  useEffect(() => {
    if (expanded && !guardrail) load().catch((e) => setError(String(e)));
  }, [expanded]);

  async function run(kind: "approve" | "reject" | "execute") {
    setBusy(kind);
    setError(null);
    try {
      if (kind === "approve") await api.approve(action.id);
      else if (kind === "reject") await api.reject(action.id, "rejected by reviewer in the queue");
      else await api.execute(action.id);
      await load();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const payload =
    typeof action.payload === "string" ? action.payload : JSON.stringify(action.payload);

  return (
    <Card className="border-border">
      <CardContent className="space-y-2 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[11px] text-muted-foreground">#{action.id}</span>
          <StatusBadge status={action.status} />
          <span className="text-xs font-semibold text-foreground">{action.action_type}</span>
          <span className="font-mono text-[11px] text-muted-foreground">{action.subject}</span>
          {action.region && (
            <Badge variant="outline" className="text-[10px]">
              {action.region}
            </Badge>
          )}
          <Badge variant="outline" className="text-[10px]">
            L{action.level}
          </Badge>
          {action.scheduled_at && (
            <span className="text-[10px] text-muted-foreground">
              for {fmtIST(action.scheduled_at)}
            </span>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="ml-auto text-[11px] font-medium text-primary hover:underline"
          >
            {expanded ? "hide" : "review"}
          </button>
        </div>

        {action.external_ref && (
          <div className="text-[11px] text-success">
            landed in the downstream system as{" "}
            <span className="font-mono">{action.external_ref}</span>
          </div>
        )}

        {expanded && (
          <div className="space-y-3 border-t border-border pt-2">
            {error && <ErrorText>{error}</ErrorText>}

            <div className="grid gap-2 text-[11px] sm:grid-cols-2">
              <div>
                <span className="text-muted-foreground">proposed by </span>
                <span className="font-mono text-foreground">{action.requested_by}</span>
              </div>
              <div>
                <span className="text-muted-foreground">approved by </span>
                <span className="font-mono text-foreground">{action.approved_by ?? "—"}</span>
              </div>
              {action.trace_id && (
                <div className="sm:col-span-2">
                  <span className="text-muted-foreground">from traced turn </span>
                  <span className="font-mono text-foreground">{action.trace_id}</span>
                </div>
              )}
            </div>

            <pre className="max-h-28 overflow-auto rounded border border-border bg-background/60 p-2 text-[10px] text-foreground/80">
              {payload}
            </pre>

            {guardrail ? (
              <GuardrailVerdict guardrail={guardrail} />
            ) : (
              <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" /> re-checking the controls…
              </div>
            )}

            {events.length > 0 && (
              <div>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Lineage
                </div>
                <Timeline events={events} />
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              {(action.status === "proposed" || action.status === "escalated") && (
                <>
                  <Button size="sm" onClick={() => run("approve")} disabled={busy !== null}>
                    {busy === "approve" ? (
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <ThumbsUp className="mr-1.5 h-3.5 w-3.5" />
                    )}
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => run("reject")}
                    disabled={busy !== null}
                  >
                    <XCircle className="mr-1.5 h-3.5 w-3.5" /> Reject
                  </Button>
                </>
              )}
              {action.status === "approved" && (
                <Button size="sm" onClick={() => run("execute")} disabled={busy !== null}>
                  {busy === "execute" ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <PlayCircle className="mr-1.5 h-3.5 w-3.5" />
                  )}
                  Execute
                </Button>
              )}
              {action.status === "escalated" && (
                <span className="inline-flex items-center gap-1 text-[11px] text-warning">
                  <ShieldX className="h-3.5 w-3.5" />
                  A control refused this at execution time, even though it had been approved.
                </span>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function Approvals({ refreshKey }: { refreshKey: number }) {
  const [actions, setActions] = useState<Action[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    setLoading(true);
    api
      .actions()
      .then((r) => setActions(r.actions))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [refreshKey, tick]);

  const open = actions.filter((a) => OPEN.has(a.status));
  const shown = showAll ? actions : open;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <SectionTitle hint="Every action an agent has proposed, with the controls that applied and the human who decided. Nothing here executed without both.">
          Approval queue
        </SectionTitle>
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => setShowAll(!showAll)}>
            {showAll ? `Open only (${open.length})` : `Show all (${actions.length})`}
          </Button>
          <Button size="sm" variant="outline" onClick={() => setTick(tick + 1)}>
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {error && <ErrorText>{error}</ErrorText>}
      {loading && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> loading the queue…
        </div>
      )}
      {!loading && shown.length === 0 && (
        <Card className="border-border">
          <CardContent className="p-4 text-xs text-muted-foreground">
            Nothing waiting. Ask a question that warrants an action, then propose it.
          </CardContent>
        </Card>
      )}
      {shown.map((a) => (
        <ActionRow key={a.id} action={a} onChanged={() => setTick(tick + 1)} />
      ))}
    </div>
  );
}
