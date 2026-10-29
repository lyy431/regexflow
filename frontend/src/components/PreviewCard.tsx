import { useState } from "react";

import type { ApplyRequest, FindReplacePreview, RegexFlag, StepRequest } from "../api/types";
import { plural } from "../utils/text";
import { FlagToggles } from "./FlagToggles";
import { ReplacedText } from "./HighlightedText";
import {
  ApplyButtons,
  ColumnsLine,
  EditedNotice,
  type PreviewBusy,
  PreviewHeader,
  SampleList,
  sameFlags,
  Summary,
} from "./PreviewParts";

interface Props {
  preview: FindReplacePreview;
  /** The plain-English request behind this preview, recorded with the step. */
  instruction: string;
  busy: PreviewBusy;
  onApply: (request: ApplyRequest) => void;
  onRerun: (request: StepRequest) => void;
  onDiscard: () => void;
}

/** Preview of a find-and-replace step. */
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
      kind: "regex_replace",
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
    onRerun({
      kind: "regex_replace",
      instruction,
      pattern,
      flags,
      replacement: effectiveReplacement,
      columns: preview.columns,
    });
  }

  return (
    <section className="card preview" aria-labelledby="preview-title">
      <PreviewHeader source={preview.source} cached={preview.cached} />
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
          <EditedNotice busy={busy} disabled={pattern === ""} onRerun={rerun}>
            You changed the pattern. Update the preview before applying it.
          </EditedNotice>
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

      <ColumnsLine columns={preview.columns} />

      <Summary empty={stats.matches === 0}>
        {stats.matches === 0
          ? "No matches. Try rephrasing your description or choosing other columns."
          : `${plural(stats.matches, "match", "matches")} in ${plural(stats.cells_changed, "cell")} across ${plural(stats.rows_affected, "row")}.`}
      </Summary>

      <SampleList
        samples={preview.samples}
        total={stats.cells_changed}
        renderAfter={(sample) =>
          effectiveReplacement === null ? (
            <span className="hint">Enter a replacement to see the result</span>
          ) : (
            <ReplacedText text={sample.before} spans={sample.spans} replacement={effectiveReplacement} />
          )
        }
      />

      <ApplyButtons busy={busy} canApply={canApply} onApply={apply} onDiscard={onDiscard} />
    </section>
  );
}
