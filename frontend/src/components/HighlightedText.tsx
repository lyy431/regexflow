import type { Span } from "../api/types";
import { segmentsFromSpans } from "../utils/text";

/** Cell text with the regex matches marked. */
export function HighlightedText({ text, spans }: { text: string; spans: Span[] }) {
  if (text === "") return <span className="empty-value">(empty)</span>;
  return (
    <>
      {segmentsFromSpans(text, spans).map((segment, index) =>
        segment.matched ? <mark key={index}>{segment.text}</mark> : <span key={index}>{segment.text}</span>,
      )}
    </>
  );
}

/** The same text after replacement, with the inserted text marked. */
export function ReplacedText({ text, spans, replacement }: { text: string; spans: Span[]; replacement: string }) {
  const segments = segmentsFromSpans(text, spans);
  if (segments.every((segment) => (segment.matched ? replacement : segment.text) === "")) {
    return <span className="empty-value">(empty)</span>;
  }
  return (
    <>
      {segments.map((segment, index) => {
        if (!segment.matched) return <span key={index}>{segment.text}</span>;
        return replacement ? <ins key={index}>{replacement}</ins> : null;
      })}
    </>
  );
}
