/** Renders the small amount of Markdown that language models emit, as React elements.
 *
 *  Genie's narrative and the supervisor's fused answer both come back with Markdown in them, e.g.
 *  `delinquency fell from **13.1%** to **10.6%**`. Rendered as plain text those asterisks are on screen
 *  in front of the customer, and the emphasis is on the figures, which is the part of the sentence a
 *  banker reads first.
 *
 *  Deliberately hand-written and deliberately NOT using dangerouslySetInnerHTML. This text is model
 *  output, so treating it as HTML would let a model, or anything that reached the model's context,
 *  inject markup into the page. Everything below produces React elements, so the content can only ever
 *  be text.
 *
 *  It covers what these models actually produce: bold, italic, inline code, fenced code, bullet lists,
 *  numbered lists and headings. Anything else is left as literal text rather than half-parsed.
 */
import type { ReactNode } from "react";

/** One line of inline Markdown to React nodes. Order matters: `**` is matched before `*`, or bold would
 *  be read as two italics. */
function inline(text: string, keyPrefix: string): ReactNode[] {
  const pattern =
    /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|(?<![\w*])\*[^*\n]+\*(?![\w*])|(?<![\w_])_[^_\n]+_(?![\w_]))/g;
  const out: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = pattern.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    const key = `${keyPrefix}-i${i++}`;
    if (tok.startsWith("**") || tok.startsWith("__")) {
      out.push(
        <strong key={key} className="font-semibold text-foreground">
          {tok.slice(2, -2)}
        </strong>
      );
    } else if (tok.startsWith("`")) {
      out.push(
        <code key={key} className="rounded bg-secondary px-1 py-0.5 font-mono text-[0.95em]">
          {tok.slice(1, -1)}
        </code>
      );
    } else {
      out.push(<em key={key}>{tok.slice(1, -1)}</em>);
    }
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ text, className }: { text: string; className?: string }) {
  const lines = (text ?? "").replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let para: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let fence: string[] | null = null;
  let n = 0;

  const flushPara = () => {
    if (!para.length) return;
    blocks.push(
      <p key={`p${n++}`} className="whitespace-pre-wrap">
        {inline(para.join(" "), `p${n}`)}
      </p>
    );
    para = [];
  };
  const flushList = () => {
    if (!list) return;
    const Tag = list.ordered ? "ol" : "ul";
    blocks.push(
      <Tag
        key={`l${n++}`}
        className={`ml-4 space-y-0.5 ${list.ordered ? "list-decimal" : "list-disc"}`}
      >
        {list.items.map((it, k) => (
          <li key={k}>{inline(it, `l${n}-${k}`)}</li>
        ))}
      </Tag>
    );
    list = null;
  };
  const flushFence = () => {
    if (!fence) return;
    blocks.push(
      <pre
        key={`c${n++}`}
        className="overflow-x-auto rounded border border-border bg-background/60 p-2 font-mono text-[11px]"
      >
        {fence.join("\n")}
      </pre>
    );
    fence = null;
  };

  for (const raw of lines) {
    if (raw.trim().startsWith("```")) {
      if (fence) flushFence();
      else {
        flushPara();
        flushList();
        fence = [];
      }
      continue;
    }
    if (fence) {
      fence.push(raw);
      continue;
    }

    const line = raw.trim();
    if (!line) {
      flushPara();
      flushList();
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flushPara();
      flushList();
      blocks.push(
        <p key={`h${n++}`} className="mt-1 font-semibold text-foreground">
          {inline(heading[2], `h${n}`)}
        </p>
      );
      continue;
    }

    const bullet = line.match(/^[-*+]\s+(.*)$/);
    const numbered = line.match(/^\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      flushPara();
      const ordered = Boolean(numbered);
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push((bullet ? bullet[1] : numbered![1]) ?? "");
      continue;
    }

    flushList();
    para.push(line);
  }
  flushPara();
  flushList();
  flushFence();

  return <div className={className ? `space-y-2 ${className}` : "space-y-2"}>{blocks}</div>;
}
