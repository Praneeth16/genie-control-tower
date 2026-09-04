/** One screen, one thread. Analytics, a live call, and the letter corpus in a single conversation.
 *
 *  These were three tabs. A banker does not think in tabs: the delinquency question, the call about the
 *  account it named, and the letter that borrower wrote are one line of enquiry, and making the user
 *  carry the account number between screens is the seam.
 *
 *  Routing between the three lanes is DETERMINISTIC and SHOWN, never inferred by a model. A second LLM
 *  hop to classify intent would cost latency and Genie quota to guess at something a regular expression
 *  settles, and a misroute nobody can see is worse than a tab. So every turn states which lane took it
 *  and why, the lane can be forced from the composer, and any turn can be re-run in another lane in one
 *  click. That is also the honest position: this is dispatch, not comprehension.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Card, CardContent } from "@databricks/appkit-ui/react";
import { BarChart3, FileSearch, Loader2, MessageSquare, Mic, MicOff, Send, Trash2 } from "lucide-react";
import { api, AskResult, Evidence, SearchResult, VoiceAssist, voiceApi } from "../../api";
import { ErrorText, SectionTitle } from "../kit";
import { AskTurn } from "./AskTurn";
import { CallTurn } from "./CallTurn";
import { EvidenceTurn, SearchTurn } from "./DocsTurn";
import { useSpeechRecognition } from "./speech";

type Lane = "ask" | "call" | "docs";

const LANE: Record<Lane, { label: string; icon: typeof MessageSquare; hint: string }> = {
  ask: {
    label: "Analysis",
    icon: BarChart3,
    hint: "Put to the supervisor, which asks whichever of the three Genie Agents the question needs",
  },
  call: {
    label: "Live call",
    icon: Mic,
    hint: "Resolved against the book, with the RBI borrower-contact window checked as the call happens",
  },
  docs: {
    label: "Documents",
    icon: FileSearch,
    hint: "Vector Search over the letters, or one complaint's record and its letter side by side",
  },
};

/** A loan account by number, or the phrase that precedes one being read aloud — in English, Hindi or
 *  Marathi, because that is the call these microfinance borrowers actually have. Spoken digits are
 *  normalised server-side, so the phrase is the signal here, not the digits. */
const CALL_HINT = /\bLN\s?\d{3,}\b|\bloan account\b|कर्ज खाते|ऋण खाता/i;

/** A complaint id. Matched only in written form: spoken digits appear inside call transcripts, which
 *  the loan-account rule above has already claimed. */
const COMPLAINT_ID = /\bCM\s?0*\d{3,}\b/i;

function normaliseComplaintId(raw: string): string {
  // Zero-padded, because COMPLAINT_ID deliberately accepts an unpadded id ("CM9245") and the backend does
  // not: documents.py only strips and uppercases, so an unpadded id came back as a confident "no record"
  // for a complaint that exists and is readable. The voice lane already pads server-side (voice.py), so
  // the same shorthand used to give two different answers depending on whether it was spoken or typed.
  const digits = raw.replace(/\D/g, "");
  return `CM${digits.padStart(7, "0")}`;
}

function detectLane(text: string): { lane: Lane; reason: string } {
  if (CALL_HINT.test(text)) {
    return { lane: "call", reason: "a loan account is named, so this is treated as a live call" };
  }
  const cm = text.match(COMPLAINT_ID);
  if (cm) {
    return {
      lane: "docs",
      reason: `complaint ${normaliseComplaintId(cm[0])} is named, so its record and letter are opened`,
    };
  }
  return { lane: "ask", reason: "no account or complaint named, so it goes to the three agents as analysis" };
}

type Turn =
  | { id: number; kind: "user"; text: string; lane: Lane; reason: string }
  | { id: number; kind: "pending"; lane: Lane }
  | { id: number; kind: "ask"; result: AskResult }
  | { id: number; kind: "call"; transcript: string; assist: VoiceAssist | null; live: boolean; error: string | null }
  | { id: number; kind: "search"; hits: SearchResult }
  | { id: number; kind: "evidence"; evidence: Evidence }
  | { id: number; kind: "error"; text: string };

/** `force` is set only where auto-routing genuinely cannot decide. A semantic phrasing names no account
 *  and no complaint, so the rules below would send it to the analysts; everything else rides the same
 *  auto path a user gets, which is the point of having the chips at all — a chip that forces its lane
 *  demonstrates nothing about routing. */
const EXAMPLES: { lane: Lane; label: string; text: string; title?: string; force?: boolean }[] = [
  {
    lane: "ask",
    label: "Solapur microfinance delinquency, and the complaints beside it",
    text:
      "Microfinance delinquency in Solapur jumped since March. Are those customers also complaining more, " +
      "and what should we do?",
  },
  {
    lane: "ask",
    label: "Why did payment-systems complaints spike in June 2026?",
    text: "Why did payment-systems complaints spike in June 2026?",
  },
  {
    lane: "ask",
    label: "RMs paid in full while failing the product-mix gate",
    text: "Which RMs are paid a full incentive while failing the product-mix quality gate?",
  },
  {
    lane: "ask",
    label: "Agents contacting borrowers outside permitted hours",
    text: "Which recovery agents are contacting borrowers outside permitted hours?",
  },
  {
    // The refusal moment needs a draft of `schedule_field_visit`, the ONLY action type the RBI
    // borrower-contact window is attached to (see action_policies). The fuser picks the action type from a
    // menu based on the evidence, so a question about AGENT conduct draws a coaching case and the refusal
    // cannot fire at all. This one is about a delinquent BORROWER and names the visit.
    lane: "ask",
    label: "Most delinquent Solapur borrowers — schedule a visit?",
    title:
      "Use this one for the refusal moment: it drafts schedule_field_visit, which is the action type the " +
      "RBI borrower-contact window governs.",
    text:
      "Which Solapur microfinance borrowers are the most delinquent, and should we schedule a recovery " +
      "field visit for the worst one?",
  },
  {
    lane: "call",
    label: "Call that must stop",
    title:
      "LN001135 — Solapur microfinance, 144 days past due and NPA, 55 prior contact attempts of which 2 " +
      "broke RBI hours, and an open grievance on the ground of Recovery agents",
    text:
      "Good morning, I'm calling about loan account L N zero zero one one three five, the microfinance " +
      "account in Solapur that has missed several instalments, and the customer is saying they have " +
      "already complained about our recovery calls under complaint C M zero zero zero nine two four five.",
  },
  {
    lane: "call",
    label: "मराठी — same call, spoken in Marathi",
    title:
      "LN001135 again, with the account number read out in Marathi. Proves the normaliser resolves " +
      "Devanagari and Roman spoken digits, not just English ones.",
    text: "कर्ज खाते एल एन शून्य शून्य एक एक तीन पाच बद्दल विचारत आहे, हप्ते थकले आहेत.",
  },
  {
    lane: "call",
    label: "Call that may proceed",
    title:
      "LN004703 — Solapur microfinance, current, contacted 80 times, no open grievance: every control clears",
    text:
      "Good morning, I'm calling about loan account L N zero zero four seven zero three to confirm the " +
      "instalment arrangement for this month.",
  },
  {
    lane: "docs",
    label: "“the agent came after dark and shouted my name”",
    text: "agent came after dark and shouted my name outside my house",
    force: true,
  },
  {
    lane: "docs",
    label: "“they told the women in my self-help group what I owe”",
    text: "they told the women in my self-help group what I owe",
    force: true,
  },
  {
    lane: "docs",
    label: "“insurance was added without my consent”",
    text: "insurance was added to my loan without my consent",
    force: true,
  },
  {
    lane: "docs",
    label: "Open CM0009245 — the LN001135 borrower's grievance",
    text: "CM0009245",
  },
];

export function Chat({ onActed }: { onActed: () => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [override, setOverride] = useState<Lane | "auto">("auto");
  const [showExamples, setShowExamples] = useState(true);

  /** Recogniser locale. Not decoration: the borrowers in this dataset are microfinance customers in
   *  Solapur and Indore, and that call happens in Marathi or Hindi. The server-side normaliser
   *  understands spoken digits in all three, in Devanagari and in Roman transliteration, because which
   *  one the Web Speech API returns depends on the recogniser and the handset. */
  const [locale, setLocale] = useState("en-IN");

  /** Which clock the conduct window is evaluated against.
   *
   *  Not a debug toggle — it is the difference between a demo that works and one that confuses. The RBI
   *  window is 08:00-19:00 IST, so a rehearsal at 20:00 IST shows a refusal on the "normal" path and the
   *  presenter has no way to show the compliant path at all. Both sides have to be reachable on demand,
   *  whatever time the room happens to be in. */
  const [clock, setClock] = useState<"now" | "in" | "out">("now");

  const [live, setLive] = useState<{ userId: number; callId: number } | null>(null);
  const [liveTranscript, setLiveTranscript] = useState("");
  const [pendingCalls, setPendingCalls] = useState<ReadonlySet<number>>(() => new Set());

  const seq = useRef(0);
  const nextId = () => ++seq.current;
  /** Per-turn request generation. Two evaluations of the SAME turn can be in flight — the presenter
   *  toggles the clock twice, or speaks again mid-lookup — and `setTurns` applies them in COMPLETION
   *  order, not issue order. Without this a superseded reply can land last and leave a verdict on screen
   *  that contradicts the selector above it. */
  const reqSeq = useRef(new Map<number, number>());
  /** Set when the mic button was pressed, cleared once the recogniser actually starts. The live turn is
   *  created from that transition rather than from the click, so a refused microphone or a synchronous
   *  throw out of `start()` leaves no orphan turn behind. */
  const wantLive = useRef(false);
  /** Which turn to bring into view. The composer is above the thread, so a new turn appears BELOW the
   *  fold once a few are stacked up; scrolling to the page bottom instead would land on the end of a long
   *  answer rather than the start of the new one. */
  const [scrollTo, setScrollTo] = useState<number | null>(null);

  const callAt = useCallback(() => {
    if (clock === "now") return Math.floor(Date.now() / 1000);
    // IST is UTC+5:30, so 10:30 IST is 05:00 UTC and 21:45 IST is 16:15 UTC. Built in UTC rather than
    // local time so the value does not shift with the presenting laptop's timezone.
    const [h, m] = clock === "in" ? [5, 0] : [16, 15];
    const d = new Date();
    return Math.floor(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), h, m, 0) / 1000);
  }, [clock]);

  /** The only place a call turn is evaluated. Live speech, the flush when the mic stops, a clock change
   *  and a typed call all route through here so they cannot disagree about ordering or error handling. */
  const evaluateCall = useCallback(
    async (callId: number, transcript: string) => {
      if (!transcript.trim()) return;
      const mine = (reqSeq.current.get(callId) ?? 0) + 1;
      reqSeq.current.set(callId, mine);
      setPendingCalls((p) => new Set(p).add(callId));
      try {
        const assist = await voiceApi.assist(transcript, callAt());
        if (reqSeq.current.get(callId) !== mine) return;   // superseded; discard
        setTurns((ts) =>
          ts.map((t) =>
            t.id === callId && t.kind === "call" ? { ...t, assist, transcript, error: null } : t
          )
        );
      } catch (e) {
        if (reqSeq.current.get(callId) !== mine) return;
        const msg = e instanceof Error ? e.message : String(e);
        // On the TURN. A banner at the foot of the thread is below the fold once a few turns stack up,
        // so a failed refresh used to leave a stale verdict looking settled and current.
        setTurns((ts) =>
          ts.map((t) => (t.id === callId && t.kind === "call" ? { ...t, error: msg } : t))
        );
      } finally {
        setPendingCalls((p) => {
          const n = new Set(p);
          n.delete(callId);
          return n;
        });
      }
    },
    [callAt]
  );

  const speech = useSpeechRecognition({
    locale,
    onFinalText: (t) => setLiveTranscript((prev) => (prev ? `${prev} ${t}` : t)),
  });

  const replace = (id: number, next: Turn) =>
    setTurns((ts) => ts.map((t) => (t.id === id ? next : t)));

  async function send(rawText: string, forced?: Lane) {
    const text = rawText.trim();
    if (!text || busy || speech.listening) return;
    const decided = forced ?? (override === "auto" ? undefined : override);
    const { lane, reason } = decided
      ? { lane: decided, reason: "lane chosen by hand" }
      : detectLane(text);

    const userId = nextId();
    const pendingId = nextId();
    setTurns((ts) => [
      ...ts,
      { id: userId, kind: "user", text, lane, reason },
      { id: pendingId, kind: "pending", lane },
    ]);
    setInput("");
    setScrollTo(userId);
    setBusy(true);
    setErr(null);
    try {
      if (lane === "ask") {
        replace(pendingId, { id: pendingId, kind: "ask", result: await api.ask(text) });
      } else if (lane === "call") {
        // The turn is placed BEFORE the lookup runs. Previously the lookup was awaited first, so a clock
        // change while it was in flight found no call turn to re-evaluate, advanced its marker, and left
        // a verdict computed against the old clock sitting under a selector that said otherwise.
        replace(pendingId, {
          id: pendingId,
          kind: "call",
          transcript: text,
          assist: null,
          live: false,
          error: null,
        });
        await evaluateCall(pendingId, text);
      } else {
        const cm = text.match(COMPLAINT_ID);
        if (cm) {
          replace(pendingId, {
            id: pendingId,
            kind: "evidence",
            evidence: await api.evidence(normaliseComplaintId(cm[0])),
          });
        } else {
          replace(pendingId, { id: pendingId, kind: "search", hits: await api.search(text) });
        }
      }
    } catch (e) {
      replace(pendingId, {
        id: pendingId,
        kind: "error",
        text: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setBusy(false);
    }
  }

  function openComplaint(complaintId: string) {
    void send(complaintId, "docs");
  }

  function micToggle() {
    if (speech.listening) {
      speech.toggle();
      return;
    }
    wantLive.current = true;
    setErr(null);
    setLiveTranscript("");
    speech.toggle();
  }

  // The live pair is opened when the recogniser REPORTS that it started, not when the button was clicked.
  // Creating it on the click left an unresolvable turn behind whenever the microphone was refused or
  // `start()` threw synchronously: nothing ever evaluated it and it span forever.
  useEffect(() => {
    if (!speech.listening || live || !wantLive.current) return;
    wantLive.current = false;
    const userId = nextId();
    const callId = nextId();
    setTurns((ts) => [
      ...ts,
      { id: userId, kind: "user", text: "Listening…", lane: "call", reason: "spoken into the microphone" },
      { id: callId, kind: "call", transcript: "", assist: null, live: true, error: null },
    ]);
    setLive({ userId, callId });
    setScrollTo(userId);
  }, [speech.listening, live]);

  // Freeze the live turn whenever the recogniser stops — including when it ends on its own or errors,
  // which is why this watches `listening` rather than living in the click handler.
  //
  // AND FLUSH. The debounced loop below is torn down the instant `live` goes null, so stopping the mic
  // within the debounce window used to discard the pending evaluation entirely: no request was ever sent,
  // and the turn froze on a spinner that could never resolve. Chrome also fires `onend` by itself on a
  // trailing pause, so this is the common path, not an edge case.
  useEffect(() => {
    if (speech.listening || !live) return;
    const { callId } = live;
    const finalText = liveTranscript;
    setTurns((ts) =>
      ts.map((t) => (t.id === callId && t.kind === "call" ? { ...t, live: false } : t))
    );
    setLive(null);
    if (finalText.trim()) void evaluateCall(callId, finalText);
  }, [speech.listening, live, liveTranscript, evaluateCall]);

  // The transcript IS the user's message on this lane, so it updates without waiting for the lookup.
  useEffect(() => {
    if (!live) return;
    const { userId } = live;
    setTurns((ts) =>
      ts.map((t) =>
        t.id === userId && t.kind === "user" ? { ...t, text: liveTranscript || "Listening…" } : t
      )
    );
  }, [liveTranscript, live]);

  // Refresh the HUD as the transcript grows, at most once every 1.5s. Firing per word would put the
  // warehouse behind the conversation.
  //
  // No in-flight gate any more. It used to skip an evaluation whose predecessor was still running and
  // simply give up, which lost the last thing said; correctness now comes from the generation token in
  // evaluateCall, so an overlapping request is safe — the stale reply is discarded rather than dropped.
  useEffect(() => {
    if (!live || !liveTranscript.trim()) return;
    const { callId } = live;
    const timer = setTimeout(() => void evaluateCall(callId, liveTranscript), 1500);
    return () => clearTimeout(timer);
  }, [liveTranscript, live, evaluateCall])

  // Changing the clock has to move the verdict on the call ALREADY on screen. In the tabbed version this
  // fell out of the lookup depending on the clock; in a thread the turn is finished, so the re-evaluation
  // has to be explicit. Without it the presenter flips to 21:45 IST and the banner keeps the old answer,
  // which is the single worst thing this screen could do.
  //
  // EVERY call turn carrying a transcript is re-evaluated, not just the newest. Two calls on screen
  // evaluated against different clocks, with nothing to tell them apart, is worse than one stale verdict.
  // An empty frozen turn (mic started, nothing said) used to shadow the real one and block the refresh.
  const prevClock = useRef(clock);
  useEffect(() => {
    if (prevClock.current === clock) return;
    prevClock.current = clock;
    for (const t of turns) {
      if (t.kind === "call" && t.transcript.trim()) void evaluateCall(t.id, t.transcript);
    }
  }, [clock, turns, evaluateCall]);

  useEffect(() => {
    if (speech.error) setErr(speech.error);
  }, [speech.error]);

  useEffect(() => {
    if (scrollTo === null) return;
    document
      .querySelector(`[data-turn="${scrollTo}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
    setScrollTo(null);
  }, [scrollTo]);

  const resolvedLane = useMemo<Lane>(
    () => (override === "auto" ? detectLane(input).lane : override),
    [override, input]
  );

  return (
    <div className="space-y-4">
      {turns.length === 0 && (
        <Card className="border-border">
          <CardContent className="space-y-3 p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <SectionTitle hint="One thread across all three lanes. Ask an analytical question, read a live call aloud, or search what borrowers wrote — the account number carries between them instead of being retyped on another screen.">
                Ask, call, or read the file
              </SectionTitle>
            </div>
            <div className="space-y-2">
              {(["ask", "call", "docs"] as Lane[]).map((l) => {
                const Icon = LANE[l].icon;
                return (
                  <div key={l}>
                    <div className="mb-1 flex items-center gap-1.5">
                      <Icon className="h-3.5 w-3.5 text-primary" />
                      <span className="text-[12px] font-semibold text-foreground">{LANE[l].label}</span>
                      <span className="text-[11px] text-muted-foreground">— {LANE[l].hint}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Composer at the TOP, in normal flow. It was a sticky bottom bar first, and that was wrong: with
          the example chips and the two call selectors it stands ~250px tall, so pinned to the viewport it
          painted straight over the conduct verdict — the one panel on this screen that decides whether an
          officer may keep talking. A composer that hides the answer is worse than one you scroll to. */}
      <Card className="border-primary/30 bg-card">
        <CardContent className="space-y-2 p-3">
          {showExamples ? (
            <div className="space-y-2 border-b border-border/60 pb-2">
              {(["ask", "call", "docs"] as Lane[]).map((l) => {
                const Icon = LANE[l].icon;
                return (
                  <div key={l} className="flex flex-wrap items-center gap-1.5">
                    <span title={LANE[l].hint} className="shrink-0">
                      <Icon className="h-3 w-3 text-primary" />
                    </span>
                    {EXAMPLES.filter((ex) => ex.lane === l).map((ex) => (
                      <button
                        key={ex.label}
                        title={ex.title ?? ex.text}
                        onClick={() => void send(ex.text, ex.force ? ex.lane : undefined)}
                        disabled={busy || speech.listening}
                        className="rounded border border-border bg-secondary/50 px-2 py-1 text-left text-[12px] text-muted-foreground hover:border-primary/40 hover:text-foreground disabled:opacity-50"
                      >
                        {ex.label}
                      </button>
                    ))}
                  </div>
                );
              })}
              <button
                onClick={() => setShowExamples(false)}
                className="text-[11px] text-muted-foreground hover:text-foreground"
              >
                hide examples
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowExamples(true)}
              className="text-[11px] text-muted-foreground hover:text-foreground"
            >
              show example questions
            </button>
          )}

          <textarea
            value={speech.listening ? liveTranscript : input}
            onChange={(e) => (speech.listening ? setLiveTranscript(e.target.value) : setInput(e.target.value))}
            rows={2}
            placeholder={
              speech.listening
                ? "Listening — speak, or type into the transcript."
                : "Ask across collections, grievance and RM performance · read a call aloud · or search the letters…"
            }
            className="w-full resize-none rounded border border-border bg-background px-3 py-2 text-sm leading-relaxed text-foreground"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(input);
              }
            }}
          />

          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              onClick={() => void send(input)}
              disabled={busy || speech.listening || !input.trim()}
            >
              {busy ? (
                <>
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> Working…
                </>
              ) : (
                <>
                  <Send className="mr-1.5 h-3.5 w-3.5" /> Send
                </>
              )}
            </Button>

            <button
              onClick={micToggle}
              disabled={!speech.supported || busy}
              title={
                speech.supported
                  ? "Speech to text runs in this browser. No audio is transmitted, stored, or sent to a model."
                  : "This browser has no Web Speech API (Firefox, and some managed desktops). Type the transcript instead — every other part of this lane works identically."
              }
              className={
                "inline-flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs font-semibold " +
                (speech.listening
                  ? "bg-destructive text-white"
                  : speech.supported && !busy
                    ? "bg-primary text-white"
                    : "cursor-not-allowed bg-muted text-muted-foreground")
              }
            >
              {speech.listening ? (
                <>
                  {/* Recording is signalled by a pulsing dot as well as the fill, the icon and the label.
                      Primary crimson and destructive red sit 1.4:1 apart in luminance, so this pair of
                      states must never rely on colour alone to tell them apart — see index.css. */}
                  <span className="relative flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-75" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-white" />
                  </span>
                  <MicOff className="h-3.5 w-3.5" />
                  Stop the call
                </>
              ) : (
                <>
                  <Mic className="h-3.5 w-3.5" />
                  Start a call
                </>
              )}
            </button>

            {/* Lane. Auto is deterministic and its decision is printed on every turn, so forcing a lane
                is a correction the room can follow rather than a hidden setting. */}
            <div className="inline-flex overflow-hidden rounded border border-border">
              {(["auto", "ask", "call", "docs"] as const).map((l) => (
                <button
                  key={l}
                  onClick={() => setOverride(l)}
                  title={l === "auto" ? "Pick the lane from what is named in the message" : LANE[l].hint}
                  className={
                    "px-2 py-1 text-[12px] font-medium " +
                    (override === l
                      ? "bg-primary text-white"
                      : "text-muted-foreground hover:bg-secondary")
                  }
                >
                  {l === "auto" ? "Auto" : LANE[l].label}
                </button>
              ))}
            </div>

            {override === "auto" && input.trim() && (
              <span className="text-[11px] text-muted-foreground">
                → {LANE[resolvedLane].label}
              </span>
            )}

            {turns.length > 0 && (
              <button
                onClick={() => {
                  if (speech.listening) speech.toggle();
                  setTurns([]);
                  setErr(null);
                }}
                className="ml-auto inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[12px] text-muted-foreground hover:text-foreground"
              >
                <Trash2 className="h-3 w-3" /> Clear thread
              </button>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3 border-t border-border/60 pt-2">
            <label className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground">
              Call language
              <select
                aria-label="Recogniser language"
                value={locale}
                disabled={speech.listening}
                title={speech.listening ? "Stop the call to change the recogniser language." : undefined}
                onChange={(e) => setLocale(e.target.value)}
                className="rounded border border-border bg-background px-1.5 py-1 text-[12px] text-foreground"
              >
                <option value="en-IN">English (India)</option>
                <option value="hi-IN">हिन्दी — Hindi</option>
                <option value="mr-IN">मराठी — Marathi</option>
              </select>
            </label>

            <label className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground">
              Evaluate conduct at
              <select
                aria-label="Conduct evaluation clock"
                value={clock}
                onChange={(e) => setClock(e.target.value as "now" | "in" | "out")}
                className="rounded border border-border bg-background px-1.5 py-1 text-[12px] text-foreground"
              >
                <option value="now">the current time</option>
                <option value="in">10:30 IST (inside the RBI window)</option>
                <option value="out">21:45 IST (outside the RBI window)</option>
              </select>
            </label>

            <span className="text-[11px] leading-relaxed text-muted-foreground">
              Analysis answers reason over 268,000 rows — expect 15–45 seconds.
            </span>
          </div>
        </CardContent>
      </Card>

      {turns.map((t) => (
        <div key={t.id} data-turn={t.id}>
          <TurnView
            turn={t}
            pending={pendingCalls.has(t.id)}
            onActed={onActed}
            onOpenComplaint={openComplaint}
            onRerun={(text, lane) => void send(text, lane)}
          />
        </div>
      ))}

      {err && <ErrorText>{err}</ErrorText>}

    </div>
  );
}

function TurnView({
  turn,
  pending,
  onActed,
  onOpenComplaint,
  onRerun,
}: {
  turn: Turn;
  pending: boolean;
  onActed: () => void;
  onOpenComplaint: (id: string) => void;
  onRerun: (text: string, lane: Lane) => void;
}) {
  if (turn.kind === "user") {
    const Icon = LANE[turn.lane].icon;
    const others = (["ask", "call", "docs"] as Lane[]).filter((l) => l !== turn.lane);
    return (
      <div className="flex flex-col items-end gap-1">
        <div className="max-w-3xl rounded-lg border border-primary/30 bg-primary/10 px-3 py-2">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{turn.text}</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-1.5">
          <span className="inline-flex items-center gap-1 rounded border border-border bg-secondary/60 px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            <Icon className="h-3 w-3" />
            {LANE[turn.lane].label} — {turn.reason}
          </span>
          {others.map((l) => (
            <button
              key={l}
              onClick={() => onRerun(turn.text, l)}
              title={LANE[l].hint}
              className="rounded border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground hover:text-foreground"
            >
              re-run as {LANE[l].label}
            </button>
          ))}
        </div>
      </div>
    );
  }

  if (turn.kind === "pending") {
    return (
      <Card className="border-border">
        <CardContent className="flex items-center gap-2 p-4 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          {turn.lane === "ask"
            ? "Asking the agents — the router picks the domains, then they run in parallel."
            : turn.lane === "call"
              ? "Resolving the call against governed tables and checking conduct…"
              : "Searching the letters…"}
        </CardContent>
      </Card>
    );
  }

  if (turn.kind === "error") return <ErrorText>{turn.text}</ErrorText>;
  if (turn.kind === "ask") return <AskTurn result={turn.result} onActed={onActed} />;
  if (turn.kind === "call")
    return (
      <CallTurn assist={turn.assist} live={turn.live} pending={pending} error={turn.error} />
    );
  if (turn.kind === "search")
    return <SearchTurn hits={turn.hits} onOpenComplaint={onOpenComplaint} />;
  return <EvidenceTurn evidence={turn.evidence} onActed={onActed} />;
}
