/** Catches a render-time throw so one bad value cannot blank the whole app mid-demo.
 *
 *  There was no boundary at all, which meant any exception thrown during render — an invalid date, a shape
 *  the backend changed — replaced the entire page with white. A governance tool that vanishes is worse than
 *  one that shows an error, and the error is what makes the failure diagnosable from the room.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Kept on the console so a QA run's pageerror listener still sees it.
    console.error("render error", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto max-w-2xl p-6">
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4">
          <h1 className="text-base font-semibold text-destructive">This screen failed to render</h1>
          <p className="mt-1 text-xs leading-relaxed text-foreground">
            The rest of the application is unaffected — reload the page to continue. Nothing was written on
            your behalf: every action in this app requires an explicit approval step.
          </p>
          <pre className="mt-3 max-h-48 overflow-auto rounded border border-border bg-card p-2 text-[11px] text-foreground/80">
            {this.state.error.message}
          </pre>
          <button
            onClick={() => window.location.reload()}
            className="mt-3 rounded bg-primary px-3 py-1.5 text-xs font-semibold text-white"
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
