import { Fragment } from "react";

import type { CleanSuggestion } from "@/lib/api";

/** Render text with {{ placeholders }} highlighted. */
export function HighlightedText({ text }: { text: string }) {
  const parts = text.split(/(\{\{.*?\}\}|\{%.*?%\})/g);
  return (
    <>
      {parts.map((part, index) =>
        /^\{[{%]/.test(part) ? (
          <mark key={index} className="rounded bg-indigo-100 px-0.5 font-mono text-indigo-800">
            {part}
          </mark>
        ) : (
          <Fragment key={index}>{part}</Fragment>
        ),
      )}
    </>
  );
}

function visible(text: string): string {
  return text.replace(/\t/g, " ⇥ ");
}

/** The suggested spot in its surrounding text (struck through), or the list items. */
export function SuggestionContextView({ suggestion }: { suggestion: CleanSuggestion }) {
  if (suggestion.anchor.action === "list") {
    return (
      <ul className="list-disc space-y-0.5 pl-5 text-xs text-slate-600">
        {suggestion.sample_text.split("\n").map((item, index) => (
          <li key={index}>{item.trim() || <span className="italic text-slate-400">(empty item)</span>}</li>
        ))}
      </ul>
    );
  }
  const { before, after } = suggestion.context;
  const match = suggestion.sample_text;
  return (
    <p className="whitespace-pre-wrap break-words rounded-md bg-slate-50 px-2 py-1.5 font-mono text-xs leading-relaxed text-slate-600">
      {before && <span>{before.length >= 60 ? "…" : ""}{visible(before)}</span>}
      {match ? (
        <mark className="rounded bg-amber-100 px-0.5 text-amber-900 line-through decoration-amber-500/60">
          {visible(match)}
        </mark>
      ) : (
        <span className="mx-0.5 rounded bg-emerald-100 px-1 text-emerald-800">＋</span>
      )}
      {after && <span>{visible(after)}{after.length >= 60 ? "…" : ""}</span>}
    </p>
  );
}
