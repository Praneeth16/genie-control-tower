/** Shared presentational primitives for the control tower. */
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Page({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mx-auto w-full max-w-6xl px-6 py-6", className)}>{children}</div>;
}

export function SectionTitle({ children, hint }: { children: ReactNode; hint?: string }) {
  return (
    <div className="mb-3">
      <h2 className="text-base font-semibold text-foreground">{children}</h2>
      {hint && <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{hint}</p>}
    </div>
  );
}

const DOMAIN_STYLES: Record<string, string> = {
  COLLECTIONS: "border-transparent bg-[oklch(0.48_0.17_18)] text-white",
  GRIEVANCE: "border-transparent bg-[oklch(0.56_0.13_255)] text-white",
  RM: "border-transparent bg-[oklch(0.60_0.14_155)] text-white",
};

export const DOMAIN_LABEL: Record<string, string> = {
  COLLECTIONS: "Collections & Recovery",
  GRIEVANCE: "Service & Grievance",
  RM: "RM Performance",
};

export function DomainBadge({ domain }: { domain: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider",
        DOMAIN_STYLES[domain] ?? "bg-muted text-muted-foreground"
      )}
    >
      {domain}
    </span>
  );
}

/** How a leg's answer was actually obtained. Never render a degraded lane as if it were a real Genie
 *  answer — the operator needs to know when they are looking at a fallback. */
export function ViaBadge({ via }: { via: string | null }) {
  const map: Record<string, { label: string; cls: string }> = {
    genie_agent: { label: "Genie Agent", cls: "bg-primary/15 text-primary border-primary/30" },
    text2sql_fallback: {
      label: "fallback (Genie unavailable)",
      cls: "bg-warning/15 text-warning border-warning/30",
    },
    throttled: { label: "throttled — quota", cls: "bg-warning/20 text-warning border-warning/40" },
    timeout: { label: "timed out", cls: "bg-warning/20 text-warning border-warning/40" },
    error: { label: "failed", cls: "bg-destructive/15 text-destructive border-destructive/30" },
  };
  const v = map[via ?? ""] ?? { label: via ?? "unknown", cls: "bg-muted text-muted-foreground" };
  return (
    <span className={cn("rounded border px-1.5 py-0.5 text-[10px] font-medium", v.cls)}>
      {v.label}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    proposed: "bg-secondary text-foreground border-border",
    approved: "bg-primary/15 text-primary border-primary/30",
    executing: "bg-primary/20 text-primary border-primary/40",
    executed: "bg-success/15 text-success border-success/30",
    rejected: "bg-muted text-muted-foreground border-border",
    failed: "bg-destructive/15 text-destructive border-destructive/30",
    escalated: "bg-warning/20 text-warning border-warning/40",
  };
  return (
    <span
      className={cn(
        "rounded border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide",
        map[status] ?? "bg-muted text-muted-foreground"
      )}
    >
      {status}
    </span>
  );
}

/** Format an instant in INDIAN STANDARD TIME.
 *
 *  Not cosmetic. Timestamps arrive from Postgres as UTC (`2026-09-04T16:15:00+00:00`), and the
 *  previous code sliced the string and printed it raw — so a field visit scheduled for 21:45 IST, and
 *  refused for being outside the 08:00-19:00 window, displayed in the queue as "16:15". In a demo
 *  whose whole subject is that window, showing the wrong side of it is worse than showing nothing.
 *
 *  Everything a bank officer reads here is local time, so IST is pinned explicitly rather than left to
 *  the viewer's browser: a colleague reviewing the queue from London must see the same time the
 *  conduct control evaluated.
 */
export function fmtIST(iso: string | null | undefined, withDate = true): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 16).replace("T", " ");
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    year: withDate ? "numeric" : undefined,
    month: withDate ? "2-digit" : undefined,
    day: withDate ? "2-digit" : undefined,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const g = (t: string) => parts.find((x) => x.type === t)?.value ?? "";
  const time = `${g("hour")}:${g("minute")} IST`;
  return withDate ? `${g("year")}-${g("month")}-${g("day")} ${time}` : time;
}

export function ErrorText({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
      {children}
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-xl font-semibold tabular-nums text-foreground">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

/** Every screen carries this. A screenshot of synthetic data must never be mistakable for a
 *  screenshot of a bank's real customers. */
export function SyntheticBadge() {
  return (
    <span className="rounded border border-warning/40 bg-warning/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-warning">
      synthetic data
    </span>
  );
}

export function RowTable({
  columns,
  rows,
  max = 12,
}: {
  columns: string[];
  rows: Record<string, unknown>[];
  max?: number;
}) {
  if (!rows.length) return <div className="text-xs text-muted-foreground">No rows returned.</div>;
  const cols = columns.length ? columns : Object.keys(rows[0]);
  return (
    <div className="overflow-x-auto rounded border border-border">
      <table className="w-full text-xs">
        <thead className="bg-secondary/60">
          <tr>
            {cols.map((c) => (
              <th key={c} className="px-2 py-1.5 text-left font-semibold text-muted-foreground">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, max).map((r, i) => (
            <tr key={i} className="border-t border-border/60">
              {cols.map((c) => (
                <td key={c} className="whitespace-nowrap px-2 py-1.5 tabular-nums text-foreground/90">
                  {r[c] === null || r[c] === undefined ? "—" : String(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > max && (
        <div className="border-t border-border bg-secondary/30 px-2 py-1 text-[10px] text-muted-foreground">
          showing {max} of {rows.length} rows
        </div>
      )}
    </div>
  );
}
