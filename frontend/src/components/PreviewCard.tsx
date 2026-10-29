import { useState } from "react";

import type { ApplyRequest, Preview, RegexFlag, ReplacementRequest } from "../api/types";
import { plural } from "../utils/text";
import { FlagToggles } from "./FlagToggles";
import { HighlightedText, ReplacedText } from "./HighlightedText";
import { Spinner } from "./Spinner";

interface Props {
  preview: Preview;
  /** The plain-English request behind this preview, recorded with the step. */
  instruction: string;
  busy: "preview" | "apply" | null;
  onApply: (request: ApplyRequest) => void;
  onRerun: (request: ReplacementRequest) => void;
  onDiscard: () => void;
}

const sameFlags = (a: RegexFlag[], b: RegexFlag[]) => a.length === b.length && a.every((flag) => b.includes(flag));

export function PreviewCard({ preview, instruction, busy, onApply, onRerun, onDiscard }: Props) {
  const [pattern, setPattern] = useState(preview.pattern);
  const [flags, setFlags] = useState<RegexFlag[]>(preview.flags);
  const [replacement, setReplacement] = useState(preview.replacement ?? "");
  const [removeMatches, setRemoveMatches] = useState(preview.replacement === "");

  // null until the user says what to put in place of the matches.
  const effectiveReplacement = removeMatches ? "" : replacement === "" ? null : replacement;
  const edited = pattern !== preview.pattern || !sameFlags(flags, preview.flags);
  const { stats } = preview;
  const canApply = busy === null && !edited && effectiveReplacement !== null && stats.matches > 0;

  function apply() {
    if (!canApply || effectiveReplacement === null) return;
    onApply({
      instruction,
      pattern: preview.pattern,
      flags: preview.flags,
      replacement: effectiveReplacement,
      columns: preview.columns,
      explanation: preview.explanation,
      source: preview.source,
    });
  }

  function rerun() {
    onRerun({ instruction, pattern, flags, replacement: effectiveReplacement, columns: preview.columns });
  }

  return (
    <section className="card preview" aria-labelledby="preview-title">
      <div className="card__header">
        <h2 id="preview-title">Preview</h2>
        <span className="badge" title="Who wrote the regular expression">
          {preview.source === "manual" ? "Your regex" : `${preview.source}${preview.cached ? " · cached" : ""}`}
        </span>
      </div>

      {preview.explanation && <p className="preview__explanation">{preview.explanation}</p>}

      <div className="field">
        <label htmlFor="preview-pattern">Regular expression</label>
        <input
          id="preview-pattern"
          className="mono"
          spellCheck={false}
          autoComplete="off"
          value={pattern}
          onChange={(event) => setPattern(event.target.value)}
        />
        <FlagToggles value={flags} onChange={setFlags} />
        {edited && (
          <div className="preview__edited">
            <span>You changed the pattern. Update the preview before applying it.</span>
            <button
              type="button"
              className="button button--small"
              onClick={rerun}
              disabled={busy !== null || pattern === ""}
            >
              {busy === "preview" ? (
                <>
                  <Spinner /> Updating…
                </>
              ) : (
                "Update preview"
              )}
            </button>
          </div>
        )}
      </div>

      <div className="field">
        <label htmlFor="preview-replacement">Replace with</label>
        <input
          id="preview-replacement"
          value={removeMatches ? "" : replacement}
          disabled={removeMatches}
          placeholder={removeMatches ? "The matched text will be removed" : "Type the replacement text"}
          onChange={(event) => setReplacement(event.target.value)}
        />
        <label className="checkbox">
          <input
            type="checkbox"
            checked={removeMatches}
            onChange={(event) => setRemoveMatches(event.target.checked)}
          />
          Remove the matched text instead
        </label>
        {effectiveReplacement === null && (
          <p className="hint hint--warning">Enter a replacement, or tick “Remove the matched text”, to apply this step.</p>
        )}
      </div>

      <div className="preview__columns">
        <span>Columns:</span>
        {preview.columns.map((column) => (
          <span className="tag" key={column}>
            {column}
          </span>
        ))}
      </div>

      <p className={`preview__summary${stats.matches === 0 ? " preview__summary--empty" : ""}`} aria-live="polite">
        {stats.matches === 0
          ? "No matches. Try rephrasing your description or choosing other columns."
          : `${plural(stats.matches, "match", "matches")} in ${plural(stats.cells_changed, "cell")} across ${plural(stats.rows_affected, "row")}.`}
      </p>

      {preview.samples.length > 0 && (
        <div className="samples">
          <h3>
            Examples
            {stats.cells_changed > preview.samples.length ? ` (first ${preview.samples.length})` : ""}
          </h3>
          <ol>
            {preview.samples.map((sample) => (
              <li key={`${sample.row}-${sample.column}`} className="sample">
                <div className="sample__where">
                  Row {(sample.row + 1).toLocaleString("en-AU")} · {sample.column}
                </div>
                <div className="sample__before">
                  <HighlightedText text={sample.before} spans={sample.spans} />
                </div>
                <div className="sample__after">
                  {effectiveReplacement === null ? (
                    <span className="hint">Enter a replacement to see the result</span>
                  ) : (
                    <ReplacedText text={sample.before} spans={sample.spans} replacement={effectiveReplacement} />
                  )}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="card__actions">
        <button type="button" className="button button--primary" disabled={!canApply} onClick={apply}>
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
    </section>
  );
}
