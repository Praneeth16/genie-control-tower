/** Genie Control Tower — three governed Genie Agents under one supervisor, with a human
 *  approval plane and the evidence to audit both.
 *
 *  All data in this application is SYNTHETIC. No real customer data is used, read or reproduced.
 */
import { useEffect, useState } from "react";
import { Badge } from "@databricks/appkit-ui/react";
import {
  AlertTriangle,
  BarChart3,
  Building2,
  ClipboardCheck,
  MessageSquare,
  ShieldCheck,
} from "lucide-react";
import { api, Health } from "./api";
import { Page, SyntheticBadge } from "./components/kit";
import { Approvals } from "./components/Approvals";
import { Dashboard } from "./components/Dashboard";
import { Governance } from "./components/Governance";
import { Chat } from "./components/chat/Chat";

type Tab = "ask" | "dashboard" | "approvals" | "governance";

// Analysis, the live call and the letter corpus were three tabs and are now one thread on the Ask
// screen: they are one line of enquiry, and making the user carry an account number between screens
// was the seam. What stays a tab is what is genuinely a different surface — a dashboard, a queue of
// pending decisions, and the governance evidence.
const TABS: { id: Tab; label: string; icon: typeof MessageSquare }[] = [
  { id: "ask", label: "Ask", icon: MessageSquare },
  { id: "dashboard", label: "Dashboard", icon: BarChart3 },
  { id: "approvals", label: "Approvals", icon: ClipboardCheck },
  { id: "governance", label: "Governance", icon: ShieldCheck },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("ask");
  const [health, setHealth] = useState<Health | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, [refreshKey]);

  const agentsReady = health ? Object.values(health.genie_agents).filter(Boolean).length : 0;

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border bg-card/60">
        <Page className="py-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <Building2 className="h-4 w-4 text-primary" />
                <span className="text-[10px] font-semibold uppercase tracking-widest text-primary">
                  Databricks · Genie Agents
                </span>
              </div>
              <h1 className="mt-1 text-xl font-bold tracking-tight text-foreground">
                Genie Control Tower
              </h1>
              <p className="mt-1 max-w-3xl text-xs leading-relaxed text-muted-foreground">
                Three governed Genie Agents — Collections &amp; Recovery, Service &amp; Grievance, RM
                Performance — under one supervisor, in one thread with live call assist and the letter
                corpus. It answers across all three, then proposes an action that a named human must
                approve and that the bank's own controls can refuse.
              </p>
            </div>
            <div className="flex flex-col items-end gap-1.5">
              <SyntheticBadge />
              {health && (
                <div className="flex flex-wrap justify-end gap-1.5">
                  <Badge variant="outline" className="text-[10px]">
                    {agentsReady}/3 agents
                  </Badge>
                  <Badge
                    variant="outline"
                    className={`text-[10px] ${health.obo_active ? "border-success/40 text-success" : "border-warning/40 text-warning"}`}
                    title={
                      health.obo_active
                        ? "Reads execute as you, so Unity Catalog row filters and column masks apply"
                        : "No forwarded user token on this request: reads run as the app service principal. Expected in local development, never in the deployed app."
                    }
                  >
                    {health.obo_active ? "reading as you" : "service identity"}
                  </Badge>
                  <Badge
                    variant="outline"
                    className="text-[10px]"
                    title={`Genie allows about ${health.genie_quota.capacity} messages per ${health.genie_quota.window_seconds}s for the whole workspace`}
                  >
                    Genie quota {health.genie_quota.used_in_window}/{health.genie_quota.capacity}
                  </Badge>
                </div>
              )}
              {health && (
                <span className="font-mono text-[10px] text-muted-foreground">
                  {health.caller}
                </span>
              )}
            </div>
          </div>

          {health && !health.obo_active && (
            <div className="mt-3 flex items-start gap-2 rounded border border-warning/40 bg-warning/10 px-3 py-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
              <p className="text-[11px] leading-relaxed text-warning">
                This request carried no forwarded user token, so business reads are running as the app
                service principal and you are seeing the whole book. That is expected locally; in the
                deployed app it would mean per-user row filtering is not in effect.
              </p>
            </div>
          )}

          <nav className="mt-4 flex gap-1">
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={`flex items-center gap-1.5 rounded-t border-b-2 px-3 py-1.5 text-xs font-medium transition-colors ${
                    active
                      ? "border-primary text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {t.label}
                </button>
              );
            })}
          </nav>
        </Page>
      </header>

      <Page>
        {tab === "ask" && <Chat onActed={() => setRefreshKey((k) => k + 1)} />}
        {tab === "dashboard" && <Dashboard />}
        {tab === "approvals" && <Approvals refreshKey={refreshKey} />}
        {tab === "governance" && <Governance />}
      </Page>

      <footer className="border-t border-border py-4">
        <Page className="py-0">
          <p className="text-[10px] leading-relaxed text-muted-foreground">
            Demonstration built on synthetic data generated for this workshop. No real customer
            data is used, read or reproduced anywhere in this application. Regulatory citations shown
            against each control describe the rule the control implements and must be confirmed by the
            bank's own compliance function before production use.
          </p>
        </Page>
      </footer>
    </div>
  );
}
