// Building blocks shared by the preview cards of the different kinds of step.
import type { ReactNode } from "react";

import type { PreviewSample, RegexFlag } from "../api/types";
import { HighlightedText } from "./HighlightedText";
import { Spinner } from "./Spinner";

/** What the workspace is waiting for, as far as a preview card is concerned. */
export type PreviewBusy = "preview" | "apply" | null;

export const sameFlags = (a: RegexFlag[], b: RegexFlag[]) =>
  a.length === b.length && a.every((flag) => b.includes(flag));

export function PreviewHeader({ source, cached }: { source: string; cached: boolean }) {
  return (
    <div className="card__header">
      <h2 id="preview-title">Preview</h2>
      <span className="badge" title="Who wrote this step">
        {source === "manual" ? "Written by you" : `${source}${cached ? " · cached" : ""}`}
      </span>
    </div>
  );
}

export function ColumnsLine({ columns }: { columns: string[] }) {
  return (
    <div className="preview__columns">
      <span>{columns.length === 1 ? "Column:" : "Columns:"}</span>
      {columns.map((column) => (
        <span className="tag" key={column}>
          {column}
        </span>
      ))}
    </div>
  );
}

export function Summary({ children, empty }: { children: ReactNode; empty: boolean }) {
  return (
    <p className={`preview__summary${empty ? " preview__summary--empty" : ""}`} aria-live="polite">
      {children}
    </p>
  );
}

interface SampleListProps {
  samples: PreviewSample[];
  /** How many cells change in total, to say whether the list is truncated. */
  total: number;
  renderAfter: (sample: PreviewSample) => ReactNode;
}

export function SampleList({ samples, total, renderAfter }: SampleListProps) {
  if (samples.length === 0) return null;
  return (
    <div className="samples">
      <h3>
        Examples
        {total > samples.length ? ` (first ${samples.length})` : ""}
      </h3>
      <ol>
        {samples.map((sample) => (
          <li key={`${sample.row}-${sample.column}`} className="sample">
            <div className="sample__where">
              Row {(sample.row + 1).toLocaleString("en-AU")} · {sample.column}
            </div>
            <div className="sample__before">
              <HighlightedText text={sample.before} spans={sample.spans} />
            </div>
            <div className="sample__after">{renderAfter(sample)}</div>
          </li>
        ))}
      </ol>
    </div>
  );
}

interface EditedNoticeProps {
  busy: PreviewBusy;
  disabled: boolean;
  onRerun: () => void;
  children: string;
}

/** Shown after the user edits a generated step: the preview must be refreshed before applying. */
export function EditedNotice({ busy, disabled, onRerun, children }: EditedNoticeProps) {
  return (
    <div className="preview__edited">
      <span>{children}</span>
      <button type="button" className="button button--small" onClick={onRerun} disabled={busy !== null || disabled}>
        {busy === "preview" ? (
          <>
            <Spinner /> Updating…
          </>
        ) : (
          "Update preview"
        )}
      </button>
    </div>
  );
}

interface ApplyButtonsProps {
  busy: PreviewBusy;
  canApply: boolean;
  onApply: () => void;
  onDiscard: () => void;
}

export function ApplyButtons({ busy, canApply, onApply, onDiscard }: ApplyButtonsProps) {
  return (
    <div className="card__actions">
      <button type="button" className="button button--primary" disabled={!canApply} onClick={onApply}>
        {busy === "apply" ? (
          <>
            <Spinner /> Applying…
          </>
        ) : (
          "Apply step"
        )}
      </button>
      <button type="button" className="button button--ghost" disabled={busy !== null} onClick={onDiscard}>
        Discard
      </button>
    </div>
  );
}
