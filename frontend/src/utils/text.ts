import type { Span } from "../api/types";

export interface Segment {
  text: string;
  matched: boolean;
}

/**
 * Split `text` into plain and matched segments. The spans come from Python and
 * count Unicode code points, so index into code points rather than UTF-16 units.
 */
export function segmentsFromSpans(text: string, spans: Span[]): Segment[] {
  const chars = Array.from(text);
  const segments: Segment[] = [];
  let cursor = 0;
  for (const [start, end] of spans) {
    if (start > cursor) segments.push({ text: chars.slice(cursor, start).join(""), matched: false });
    segments.push({ text: chars.slice(start, end).join(""), matched: true });
    cursor = end;
  }
  if (cursor < chars.length) segments.push({ text: chars.slice(cursor).join(""), matched: false });
  return segments;
}

/** Replace every span with `replacement`, inserted literally, as the server does. */
export function applySpans(text: string, spans: Span[], replacement: string): string {
  return segmentsFromSpans(text, spans)
    .map((segment) => (segment.matched ? replacement : segment.text))
    .join("");
}

export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${count.toLocaleString("en-AU")} ${count === 1 ? singular : pluralForm}`;
}
