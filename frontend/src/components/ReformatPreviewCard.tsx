import { useState } from "react";

import type { ApplyRequest, ReformatPreview, RegexFlag, StepRequest } from "../api/types";
import { plural } from "../utils/text";
import { FlagToggles } from "./FlagToggles";
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
  preview: ReformatPreview;
  /** The plain-English request behind this preview, recorded with the step. */
  instruction: string;
  busy: PreviewBusy;
  onApply: (request: ApplyRequest) => void;
  onRerun: (request: StepRequest) => void;
  onDiscard: () => void;
}

/** Preview of a step that rewrites values into a new format. */
export function ReformatPreviewCard({ preview, instruction, busy, onApply, onRerun, onDiscard }: Props) {
  const [pattern, setPattern] = useState(preview.pattern);
  const [flags, setFlags] = useState<RegexFlag[]>(preview.flags);
  const [template, setTemplate] = useState(preview.template);

  const edited = pattern !== preview.pattern || template !== preview.template || !sameFlags(flags, preview.flags);
  const { stats } = preview;
  const canApply = busy === null && !edited && stats.cells_changed > 0;

  function apply() {
    if (!canApply) return;
    onApply({
      kind: "reformat",
      instruction,
      pattern: preview.pattern,
      flags: preview.flags,
      template: preview.template,
      columns: preview.columns,
      explanation: preview.explanation,
      source: preview.source,
    });
  }

  function rerun() {
    onRerun({ kind: "reformat", instruction, pattern, flags, template, columns: preview.columns });
  }

  return (
    <section className="card preview" aria-labelledby="preview-title">
      <PreviewHeader source={preview.source} cached={preview.cached} />
      {preview.explanation && <p className="preview__explanation">{preview.explanation}</p>}

      <div className="field">
        <label htmlFor="reformat-pattern">Find (regular expression with named groups)</label>
        <input
          id="reformat-pattern"
          className="mono"
          spellCheck={false}
          autoComplete="off"
          value={pattern}
          onChange={(event) => setPattern(event.target.value)}
        />
        <FlagToggles value={flags} onChange={setFlags} />
      </div>

      <div className="field">
        <label htmlFor="reformat-template">Rewrite as</label>
        <input
          id="reformat-template"
          className="mono"
          spellCheck={false}
          autoComplete="off"
          value={template}
          onChange={(event) => setTemplate(event.target.value)}
        />
        <p className="hint">
          <code>{"\\g<name>"}</code> inserts the part captured by the group of that name; everything else is kept as
          written.
        </p>
        {edited && (
          <EditedNotice busy={busy} disabled={pattern === "" || template === ""} onRerun={rerun}>
            You changed the rewrite. Update the preview before applying it.
          </EditedNotice>
        )}
      </div>

      <ColumnsLine columns={preview.columns} />

      <Summary empty={stats.cells_changed === 0}>
        {stats.cells_changed > 0
          ? `${plural(stats.cells_changed, "value")} will be rewritten, across ${plural(stats.rows_affected, "row")}.`
          : stats.matches > 0
            ? "Every matching value is already in the target format."
            : "No values match. Try rephrasing your description or choosing other columns."}
      </Summary>

      <SampleList samples={preview.samples} total={stats.cells_changed} renderAfter={(sample) => sample.after} />

      <ApplyButtons busy={busy} canApply={canApply} onApply={apply} onDiscard={onDiscard} />
    </section>
  );
}
