/** The embedded AI/BI dashboard.
 *
 *  Why this tab exists next to Ask: a Genie Agent answers the question you thought to ask, and a
 *  dashboard shows you the thing you did not. Bank reviews need both, and putting them behind one
 *  identity is the point — the dashboard is published WITHOUT embedded credentials, so its tiles run
 *  as the signed-in viewer under the same Unity Catalog row filters and column masks as the agents.
 *  The two surfaces therefore cannot disagree with each other, which is the failure a governance team
 *  actually worries about.
 */
import { useEffect, useState } from "react";
import { BarChart3, ExternalLink } from "lucide-react";
import { api } from "../api";
import { ErrorText, Page, SectionTitle, SyntheticBadge } from "./kit";

export function Dashboard() {
  const [info, setInfo] = useState<{ dashboard_id: string | null; workspace_host: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.dashboard().then(setInfo).catch((e) => setErr(String(e.message || e)));
  }, []);

  if (err) return <Page><ErrorText>{err}</ErrorText></Page>;
  if (!info) return <Page><div className="text-xs text-muted-foreground">Loading dashboard…</div></Page>;

  if (!info.dashboard_id) {
    return (
      <Page>
        <ErrorText>
          No dashboard is configured. Publish one with{" "}
          <code>python3 dashboards/build_dashboard.py --deploy</code> and set <code>DASHBOARD_ID</code>.
        </ErrorText>
      </Page>
    );
  }

  const host = info.workspace_host.replace(/\/$/, "");
  const embed = `${host}/embed/dashboardsv3/${info.dashboard_id}`;
  const full = `${host}/dashboardsv3/${info.dashboard_id}/published`;

  return (
    <Page>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <SectionTitle hint="Published without embedded credentials, so every tile runs as you — the same row filters and column masks that govern the Genie Agents govern this page.">
          <span className="inline-flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-primary" />
            Portfolio, service and incentive integrity
          </span>
        </SectionTitle>
        <div className="flex items-center gap-2">
          <SyntheticBadge />
          <a
            href={full}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[11px] font-medium text-foreground hover:bg-secondary"
          >
            Open in workspace <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      </div>

      {/* An iframe is the supported embed path. It carries the viewer's own Databricks session, which
          is exactly what we want: nothing here runs as the app service principal. A viewer who is not
          entitled to the dashboard sees the workspace's own permission error rather than our data. */}
      <iframe
        src={embed}
        title="Control Tower dashboard"
        className="h-[calc(100vh-15rem)] min-h-[38rem] w-full rounded-lg border border-border bg-card"
      />

      <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
        If the frame is blank, open the dashboard in the workspace once to establish the session — the
        embed carries your browser session and cannot mint one of its own.
      </p>
    </Page>
  );
}
