import { useState } from "react";

import type { ApplyRequest, NormalizePreview } from "../api/types";
import { plural } from "../utils/text";
import { ApplyButtons, type PreviewBusy, PreviewHeader, Summary } from "./PreviewParts";

interface Props {
  preview: NormalizePreview;
  /** The goal the user gave, recorded with the step. */
  instruction: string;
  busy: PreviewBusy;
  onApply: (request: ApplyRequest) => void;
  onDiscard: () => void;
}

interface Row {
  from: string;
  to: string;
  count: number;
  include: boolean;
}

/** Preview of a step that maps the variants of each value in one column to one form. */
export function NormalizePreviewCard({ preview, instruction, busy, onApply, onDiscard }: Props) {
  const [rows, setRows] = useState<Row[]>(() => preview.mapping.map((row) => ({ ...row, include: true })));

  // The mapping as the user left it: ticked rows whose new value is not blank or unchanged.
  const chosen = rows.filter((row) => row.include && row.to.trim() !== "" && row.to !== row.from);
  const cellsToChange = chosen.reduce((total, row) => total + row.count, 0);
  const canApply = busy === null && chosen.length > 0;

  function update(index: number, change: Partial<Row>) {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...change } : row)));
  }

  function apply() {
    if (!canApply) return;
    onApply({
      kind: "normalize_values",
      column: preview.column,
      instruction,
      mapping: Object.fromEntries(chosen.map((row) => [row.from, row.to])),
      explanation: preview.explanation,
      source: preview.source,
    });
  }

  return (
    <section className="card preview" aria-labelledby="preview-title">
      <PreviewHeader source={preview.source} cached={preview.cached} />
      {preview.explanation && <p className="preview__explanation">{preview.explanation}</p>}

      {rows.length === 0 ? (
        <Summary empty>All values in “{preview.column}” already look consistent. Nothing to change.</Summary>
      ) : (
        <>
          <table className="mapping-table">
            <caption>
              Proposed changes in <strong>{preview.column}</strong>. Untick a row or edit the new value before applying.
            </caption>
            <thead>
              <tr>
                <th scope="col">Use</th>
                <th scope="col">Current value</th>
                <th scope="col">New value</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={row.from} className={row.include ? undefined : "mapping-table__off"}>
                  <td>
                    <input
                      type="checkbox"
                      checked={row.include}
                      aria-label={`Change “${row.from}”`}
                      onChange={(event) => update(index, { include: event.target.checked })}
                    />
                  </td>
                  <td>
                    <span className="mapping-table__from">{row.from}</span>
                    <span className="mapping-table__count">×{row.count.toLocaleString("en-AU")}</span>
                  </td>
                  <td>
                    <input
                      value={row.to}
                      disabled={!row.include}
                      aria-label={`New value for “${row.from}”`}
                      onChange={(event) => update(index, { to: event.target.value })}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Summary empty={chosen.length === 0}>
            {chosen.length === 0
              ? "No change selected."
              : `${plural(chosen.length, "value")} will be replaced in ${plural(cellsToChange, "cell")}.`}
          </Summary>
        </>
      )}

      <ApplyButtons busy={busy} canApply={canApply} onApply={apply} onDiscard={onDiscard} />
    </section>
  );
}
