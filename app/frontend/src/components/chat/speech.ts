/** Browser speech recognition, extracted so the chat composer can own the microphone.
 *
 *  Speech to text runs in THIS BROWSER via the Web Speech API. No audio leaves the device; only the
 *  transcript crosses to the server. That is a governance property, not an implementation detail.
 *
 *  Recognition is unavailable in Firefox and on some managed desktops, so `supported` is surfaced and
 *  the typed path must always remain usable — a demo drivable only by voice is a demo that fails in a
 *  room with bad acoustics.
 */
import { useCallback, useEffect, useRef, useState } from "react";

/** Minimal shape of the vendor-prefixed Web Speech API. Typed locally because it is not in lib.dom. */
type Recognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult:
    | ((e: {
        resultIndex: number;
        results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
      }) => void)
    | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
};

function recognitionCtor(): (new () => Recognition) | null {
  const w = window as unknown as Record<string, new () => Recognition>;
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export function useSpeechRecognition({
  locale,
  onFinalText,
}: {
  locale: string;
  onFinalText: (text: string) => void;
}) {
  const [supported] = useState(() => recognitionCtor() !== null);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<Recognition | null>(null);

  // Held in a ref so a changing callback identity never restarts a live recogniser mid-sentence.
  const sink = useRef(onFinalText);
  sink.current = onFinalText;

  const stop = useCallback(() => {
    rec.current?.stop();
    rec.current = null;
    setListening(false);
  }, []);

  const start = useCallback(() => {
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    const r = new Ctor();
    r.continuous = true;
    r.interimResults = true;
    r.lang = locale;
    r.onresult = (e) => {
      let finalText = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        // Guard the alternative index: a result with no alternatives would otherwise throw inside the
        // event handler and lose the phrase silently.
        const alt = e.results[i].isFinal ? e.results[i][0] : undefined;
        if (alt?.transcript) finalText += alt.transcript + " ";
      }
      if (finalText) sink.current(finalText.trim());
    };
    r.onerror = (e) => {
      setError(`speech recognition: ${e.error}`);
      setListening(false);
    };
    r.onend = () => setListening(false);
    rec.current = r;
    setError(null);
    // `start()` throws synchronously on a non-secure origin and with InvalidStateError if a recogniser is
    // already running. Uncaught, that propagated out of a React event handler after the caller had already
    // committed state for a call that never began.
    try {
      r.start();
    } catch (e) {
      rec.current = null;
      setError(`could not start the microphone: ${e instanceof Error ? e.message : String(e)}`);
      setListening(false);
      return;
    }
    setListening(true);
  }, [locale]);

  const toggle = useCallback(() => {
    if (listening) stop();
    else start();
  }, [listening, start, stop]);

  // Never leave the microphone open when the screen unmounts.
  useEffect(() => () => rec.current?.stop(), []);

  return { supported, listening, error, toggle, stop };
}
