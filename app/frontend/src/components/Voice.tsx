/** Voice lane — AGENT ASSIST for a live call.
 *
 *  Read the note at the top of backend/voice.py for why this is assist and not a customer-facing bot.
 *  The short version: the Databricks voice reference stack measures 30-40s end to end today, which is
 *  fatal to self-service and fine for assist, and putting a generative voice in front of a retail
 *  borrower is an RBI conduct exposure a bank should not take on in a first project.
 *
 *  Speech to text runs in THIS BROWSER via the Web Speech API. No audio leaves the device. What
 *  crosses to the server is the transcript, and what comes back is governed data plus the same RBI
 *  conduct verdict the action plane enforces — live, while the officer is still on the call.
 *
 *  The typed box below the microphone is not a fallback afterthought. Speech recognition is
 *  unavailable in Firefox and on some managed desktops, and a demo that can only be driven by voice
 *  is a demo that fails in a room with bad acoustics. The typed path is always present and always works.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Mic, MicOff, ShieldCheck } from "lucide-react";
import { voiceApi, VoiceAssist } from "../api";
import { ErrorText, Page, RowTable, SectionTitle, Stat, SyntheticBadge } from "./kit";

/** Minimal shape of the vendor-prefixed Web Speech API. Typed locally because it is not in lib.dom. */
type Recognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
};

function recognitionCtor(): (new () => Recognition) | null {
  const w = window as unknown as Record<string, new () => Recognition>;
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

/** Two sample calls: one where the controls stop the officer, one where they clear them.
 *
 *  Both are Solapur microfinance, so they sit inside the narrative the rest of the demo builds. The
 *  pair matters: a HUD that only ever shows red is a red-light machine nobody trusts, and the
 *  compliant call is what makes the refusal mean something.
 *
 *  LN001135 is worth understanding, because it is the whole argument in one row. The borrower is 144
 *  days past due and classified NPA. Recovery has contacted them 55 times, twice outside the hours RBI
 *  permits. And they have an open grievance whose RBI ground is **Recovery agents** — they are
 *  complaining about the conduct of the collection itself. That chain exists because complaints are now
 *  generated from actual recovery pressure rather than assigned to random customers; before that fix no
 *  account in the book was simultaneously past due, contacted, and grieving, and the grievance-hold
 *  control had nothing real to fire on.
 *
 *  Account numbers are spoken as digits on purpose: that is how an officer reads one aloud, and it
 *  exercises the transcription normaliser rather than tiptoeing around it.
 */
const SAMPLES: { label: string; hint: string; text: string }[] = [
  {
    label: "Call that must stop",
    hint:
      "LN001135 — Solapur microfinance, 144 days past due and NPA, 55 prior contact attempts of which " +
      "2 broke RBI hours, and an open grievance on the ground of Recovery agents",
    text:
      "Good morning, I'm calling about loan account L N zero zero one one three five, the microfinance " +
      "account in Solapur that has missed several instalments, and the customer is saying they have " +
      "already complained about our recovery calls under complaint C M zero zero zero nine two four five.",
  },
  {
    label: "मराठी — same call, spoken in Marathi",
    hint:
      "LN001135 again, with the account number read out in Marathi. Proves the normaliser resolves " +
      "Devanagari and Roman spoken digits, not just English ones.",
    text: "कर्ज खाते एल एन शून्य शून्य एक एक तीन पाच बद्दल विचारत आहे, हप्ते थकले आहेत.",
  },
  {
    label: "Call that may proceed",
    hint: "LN004703 — Solapur microfinance, current, contacted 80 times, no open grievance: every control clears",
    text:
      "Good morning, I'm calling about loan account L N zero zero four seven zero three to confirm the " +
      "instalment arrangement for this month.",
  },
];

export function Voice() {
  const [supported] = useState(() => recognitionCtor() !== null);
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [assist, setAssist] = useState<VoiceAssist | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** Which clock the conduct window is evaluated against.
   *
   *  Not a debug toggle — it is the difference between a demo that works and one that confuses. The
   *  RBI window is 08:00-19:00 IST, so a rehearsal at 20:00 IST shows a refusal on the "normal" path
   *  and the presenter has no way to show the compliant path at all. Both sides have to be reachable
   *  on demand, whatever time the room happens to be in. */
  const [clock, setClock] = useState<"now" | "in" | "out">("now");
  /** Recogniser locale. Not decoration: the borrowers in this dataset are microfinance customers in
   *  Solapur and Indore, and that call happens in Marathi or Hindi. The server-side normaliser
   *  understands spoken digits in all three, in Devanagari and in Roman transliteration, because which
   *  one the Web Speech API returns depends on the recogniser and the handset. */
  const [locale, setLocale] = useState("en-IN");

  const rec = useRef<Recognition | null>(null);
  const inflight = useRef(false);

  const callAt = useCallback(() => {
    if (clock === "now") return Math.floor(Date.now() / 1000);
    // IST is UTC+5:30, so 10:30 IST is 05:00 UTC and 21:45 IST is 16:15 UTC. Built in UTC rather than
    // local time so the value does not shift with the presenting laptop's timezone.
    const [h, m] = clock === "in" ? [5, 0] : [16, 15];
    const d = new Date();
    return Math.floor(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), h, m, 0) / 1000);
  }, [clock]);

  const refresh = useCallback(
    async (text: string) => {
      if (!text.trim() || inflight.current) return;
      inflight.current = true;
      setBusy(true);
      try {
        setAssist(await voiceApi.assist(text, callAt()));
        setErr(null);
      } catch (e) {
        setErr(String((e as Error).message || e));
      } finally {
        inflight.current = false;
        setBusy(false);
      }
    },
    [callAt]
  );

  // Refresh the HUD as the transcript grows, but never more than once every 1.5s and never while a
  // request is already in flight. Firing per word would put the warehouse behind the conversation.
  useEffect(() => {
    if (!transcript.trim()) return;
    // `refresh` changes identity when the clock selector changes, so this also re-evaluates conduct
    // the moment the presenter switches clocks — without that the banner keeps the previous verdict.
    const t = setTimeout(() => refresh(transcript), 1500);
    return () => clearTimeout(t);
  }, [transcript, refresh]);

  const toggle = () => {
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    if (listening) {
      rec.current?.stop();
      setListening(false);
      return;
    }
    const r = new Ctor();
    r.continuous = true;
    r.interimResults = true;
    r.lang = locale;
    r.onresult = (e) => {
      let finalText = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalText += e.results[i][0].transcript + " ";
      }
      if (finalText) setTranscript((prev) => (prev + " " + finalText).trim());
    };
    r.onerror = (e) => {
      setErr(`speech recognition: ${e.error}`);
      setListening(false);
    };
    r.onend = () => setListening(false);
    rec.current = r;
    r.start();
    setListening(true);
  };

  const conductFail = (assist?.conduct || []).filter((c) => !c.passed);

  return (
    <Page>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <SectionTitle hint="Speech to text runs in this browser — no audio is transmitted, stored, or sent to a model. Only the transcript reaches the server, and the account facts come back under your own Unity Catalog entitlements.">
          Live call assist
        </SectionTitle>
        <SyntheticBadge />
      </div>

      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={toggle}
            disabled={!supported}
            className={
              "inline-flex items-center gap-2 rounded px-3 py-1.5 text-xs font-semibold " +
              (listening
                ? "bg-destructive text-white"
                : supported
                  ? "bg-primary text-white"
                  : "cursor-not-allowed bg-muted text-muted-foreground")
            }
          >
            {listening ? <MicOff className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />}
            {listening ? "Stop listening" : "Start listening"}
          </button>

          <label className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
            Language
            <select
              aria-label="Recogniser language"
              value={locale}
              onChange={(e) => setLocale(e.target.value)}
              className="rounded border border-border bg-background px-1.5 py-1 text-[11px] text-foreground"
            >
              <option value="en-IN">English (India)</option>
              <option value="hi-IN">हिन्दी — Hindi</option>
              <option value="mr-IN">मराठी — Marathi</option>
            </select>
          </label>

          <label className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
            Evaluate conduct at
            <select
              aria-label="Conduct evaluation clock"
              value={clock}
              onChange={(e) => setClock(e.target.value as "now" | "in" | "out")}
              className="rounded border border-border bg-background px-1.5 py-1 text-[11px] text-foreground"
            >
              <option value="now">the current time</option>
              <option value="in">10:30 IST (inside the RBI window)</option>
              <option value="out">21:45 IST (outside the RBI window)</option>
            </select>
          </label>

          {SAMPLES.map((sm) => (
            <button
              key={sm.label}
              title={sm.hint}
              onClick={() => setTranscript(sm.text)}
              className="rounded border border-border px-2 py-1 text-[11px] font-medium hover:bg-secondary"
            >
              {sm.label}
            </button>
          ))}
          <button
            onClick={() => {
              setTranscript("");
              setAssist(null);
            }}
            className="rounded border border-border px-2 py-1 text-[11px] font-medium hover:bg-secondary"
          >
            Clear
          </button>
          {busy && <span className="text-[11px] text-muted-foreground">looking up…</span>}
        </div>

        {!supported && (
          <p className="mt-2 text-[11px] leading-relaxed text-warning">
            This browser has no Web Speech API (Firefox, and some managed desktops). Type or paste the
            transcript below — every other part of this lane works identically.
          </p>
        )}

        <textarea
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          rows={3}
          placeholder="Transcript appears here as you speak, or type it."
          className="mt-3 w-full rounded border border-border bg-background px-3 py-2 text-xs leading-relaxed text-foreground"
        />
      </div>

      {err && (
        <div className="mt-3">
          <ErrorText>{err}</ErrorText>
        </div>
      )}

      {assist && (
        <>
          {/* Conduct verdict first, and unmissable. On a live call this is the only thing that changes
              what the officer is allowed to say next, so it outranks the account detail below it. */}
          <div className="mt-4">
            <SectionTitle hint="The same Unity Catalog controls the action plane enforces, evaluated against this call's clock. Verified as the service principal, never on your behalf — a check you could blind with your own row filters would not be a check.">
              Conduct
            </SectionTitle>
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
                    <div className="font-semibold">{c.rule}</div>
                    <div className="text-muted-foreground">{c.detail}</div>
                    <div className="mt-0.5 inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                      <ShieldCheck className="h-3 w-3" />
                      verified by {c.verified_by}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {conductFail.length > 0 && (
              <p className="mt-2 text-[11px] font-semibold text-destructive">
                {conductFail.length} control(s) failed — do not proceed with recovery on this call.
              </p>
            )}
          </div>

          <div className="mt-4">
            <SectionTitle hint="Heard in the call and resolved against governed tables.">
              What the call is about
            </SectionTitle>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Loan account" value={assist.entities.loan_account_id || "—"} />
              <Stat label="Complaint" value={assist.entities.complaint_id || "—"} />
              <Stat label="Customer" value={assist.customer_id || "—"} sub="pseudonymised by column mask" />
              <Stat
                label="Open grievances"
                value={String(assist.grievance?.open_complaints ?? "—")}
                sub={assist.grievance?.open_ground ? String(assist.grievance.open_ground) : undefined}
              />
            </div>

            {assist.not_visible && (
              <p className="mt-2 text-[11px] leading-relaxed text-warning">
                An identifier was recognised but no record came back. Under on-behalf-of-user auth that
                means it is <strong>outside your entitlement</strong> — it does not mean the record does
                not exist. Escalate rather than telling the customer there is no such account.
              </p>
            )}
          </div>

          {assist.loan && (
            <div className="mt-4">
              <SectionTitle>Account</SectionTitle>
              <RowTable columns={[]} rows={[assist.loan]} />
            </div>
          )}
          {assist.contact && (
            <div className="mt-4">
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
            <div className="mt-4">
              <SectionTitle>Referenced complaint</SectionTitle>
              <RowTable columns={[]} rows={[assist.complaint]} />
              <p className="mt-1 text-[11px] text-muted-foreground">
                Received {String(assist.complaint.received_date ?? "—")} (date only — no time is
                recorded on a complaint, so none is shown)
              </p>
            </div>
          )}
        </>
      )}
    </Page>
  );
}
