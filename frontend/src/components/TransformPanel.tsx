import { useState, type FormEvent, type KeyboardEvent } from "react";

import type { Column, RegexFlag, StepKind, StepRequest } from "../api/types";
import { FlagToggles } from "./FlagToggles";
import { Spinner } from "./Spinner";

export const STEP_KINDS: { kind: StepKind; label: string }[] = [
  { kind: "regex_replace", label: "Find & replace" },
  { kind: "reformat", label: "Standardise format" },
  { kind: "normalize_values", label: "Normalise values" },
];

export const EXAMPLES: Record<StepKind, string[]> = {
  regex_replace: [
    "Find email addresses and replace them with 'REDACTED'",
    "Mask Australian mobile numbers with '[phone]'",
    "Replace website links with '[link]'",
    "Remove the word 'urgent' in any capitalisation",
  ],
  reformat: [
    "Convert dates like 31/01/2024 to 2024-01-31",
    "Format mobile numbers as +61 4XX XXX XXX",
    "Rewrite names like 'Doe, John' as 'John Doe'",
  ],
  normalize_values: [
    "Use the official Australian state abbreviations",
    "Write each country the same way",
    "Use consistent capitalisation",
  ],
};

type Mode = "describe" | "regex";

interface Props {
  columns: Column[];
  busy: boolean;
  /** null while unknown; false when the server has no LLM configured. */
  llmAvailable: boolean | null;
  onPreview: (request: StepRequest) => void;
}

/** The form for a new step: pick its kind, describe it (or write the regex), then preview it. */
export function TransformPanel({ columns, busy, llmAvailable, onPreview }: Props) {
  const [kind, setKind] = useState<StepKind>("regex_replace");
  const [chosenMode, setChosenMode] = useState<Mode>("describe");
  const [instructions, setInstructions] = useState<Record<StepKind, string>>({
    regex_replace: "",
    reformat: "",
    normalize_values: "",
  });
  const [pattern, setPattern] = useState("");
  const [flags, setFlags] = useState<RegexFlag[]>([]);
  const [replacement, setReplacement] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [normalizeColumn, setNormalizeColumn] = useState("");

  const needsLlm = llmAvailable === false;
  const mode: Mode = needsLlm ? "regex" : chosenMode;
  const instruction = instructions[kind];
  const setInstruction = (text: string) => setInstructions((current) => ({ ...current, [kind]: text }));

  const ready =
    kind === "regex_replace"
      ? mode === "describe"
        ? instruction.trim() !== ""
        : pattern !== ""
      : !needsLlm && (kind === "reformat" ? instruction.trim() !== "" : normalizeColumn !== "");
  const canSubmit = !busy && ready;

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!canSubmit) return;
    if (kind === "normalize_values") {
      onPreview({ kind, column: normalizeColumn, instruction: instruction.trim() });
    } else if (kind === "reformat") {
      onPreview({ kind, instruction: instruction.trim(), columns: selected });
    } else {
      // A blank field means "not specified": the instruction may say what to use.
      const shared = { kind, replacement: replacement === "" ? null : replacement, columns: selected } as const;
      onPreview(mode === "describe" ? { ...shared, instruction: instruction.trim() } : { ...shared, pattern, flags });
    }
  }

  function submitOnCtrlEnter(event: KeyboardEvent) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) submit();
  }

  return (
    <form className="card transform" onSubmit={submit}>
      <div className="card__header">
        <h2>New step</h2>
      </div>

      <div className="kind-tabs" role="tablist" aria-label="Kind of step">
        {STEP_KINDS.map((option) => (
          <button
            type="button"
            role="tab"
            key={option.kind}
            aria-selected={kind === option.kind}
            className="kind-tabs__tab"
            onClick={() => setKind(option.kind)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {kind === "regex_replace" && (
        <>
          <div className="segmented segmented--block" role="group" aria-label="How to define the pattern">
            <button type="button" aria-pressed={mode === "describe"} disabled={needsLlm} onClick={() => setChosenMode("describe")}>
              Describe it
            </button>
            <button type="button" aria-pressed={mode === "regex"} onClick={() => setChosenMode("regex")}>
              Write a regex
            </button>
          </div>
          {needsLlm && (
            <p className="hint hint--warning">
              No language model is configured on this server, so write the regular expression yourself.
            </p>
          )}
          {mode === "describe" ? (
            <DescriptionField
              label="What should be found?"
              placeholder="e.g. Find email addresses in the Email column and replace them with 'REDACTED'"
              value={instruction}
              examples={EXAMPLES.regex_replace}
              onChange={setInstruction}
              onKeyDown={submitOnCtrlEnter}
            />
          ) : (
            <div className="field">
              <label htmlFor="pattern">Regular expression (Python syntax)</label>
              <input
                id="pattern"
                className="mono"
                maxLength={1000}
                spellCheck={false}
                autoComplete="off"
                value={pattern}
                placeholder="e.g. \b[\w.+-]+@[\w-]+\.[\w.]+\b"
                onChange={(event) => setPattern(event.target.value)}
              />
              <FlagToggles value={flags} onChange={setFlags} />
            </div>
          )}
          <div className="field">
            <label htmlFor="replacement">
              Replace with{" "}
              <span className="optional">{mode === "describe" ? "(optional if your description says it)" : "(optional)"}</span>
            </label>
            <input
              id="replacement"
              maxLength={1000}
              value={replacement}
              placeholder="e.g. REDACTED"
              onChange={(event) => setReplacement(event.target.value)}
            />
          </div>
          <ColumnPicker
            columns={columns}
            selected={selected}
            onChange={setSelected}
            hint={
              mode === "describe"
                ? "None selected: the columns your description names, otherwise every text column."
                : "None selected: every text column."
            }
          />
        </>
      )}

      {kind === "reformat" && (
        <>
          <NeedsLlmHint show={needsLlm} />
          <DescriptionField
            label="How should the values be rewritten?"
            placeholder="e.g. Convert dates like 31/01/2024 to 2024-01-31"
            value={instruction}
            examples={EXAMPLES.reformat}
            onChange={setInstruction}
            onKeyDown={submitOnCtrlEnter}
          />
          <ColumnPicker
            columns={columns}
            selected={selected}
            onChange={setSelected}
            hint="None selected: the columns your description names, otherwise every text column."
          />
        </>
      )}

      {kind === "normalize_values" && (
        <>
          <NeedsLlmHint show={needsLlm} />
          <div className="field">
            <label htmlFor="normalize-column">Column to clean up</label>
            <select
              id="normalize-column"
              value={normalizeColumn}
              onChange={(event) => setNormalizeColumn(event.target.value)}
            >
              <option value="">Choose a column…</option>
              {columns.map((column) => (
                <option key={column.name} value={column.name}>
                  {column.name}
                </option>
              ))}
            </select>
          </div>
          <DescriptionField
            label="Goal"
            optional="(optional)"
            placeholder="e.g. Use the official Australian state abbreviations"
            value={instruction}
            examples={EXAMPLES.normalize_values}
            onChange={setInstruction}
            onKeyDown={submitOnCtrlEnter}
            rows={2}
          />
          <p className="hint">
            Works on columns with a limited set of values, such as states, countries or statuses. This step sends the
            column's distinct values to the language model; the other steps only send column names.
          </p>
        </>
      )}

      <button type="submit" className="button button--primary button--block" disabled={!canSubmit}>
        {busy ? (
          <>
            <Spinner /> Generating preview…
          </>
        ) : (
          "Preview changes"
        )}
      </button>
    </form>
  );
}

interface DescriptionFieldProps {
  label: string;
  optional?: string;
  placeholder: string;
  value: string;
  examples: string[];
  rows?: number;
  onChange: (text: string) => void;
  onKeyDown: (event: KeyboardEvent) => void;
}

function DescriptionField({ label, optional, placeholder, value, examples, rows = 3, onChange, onKeyDown }: DescriptionFieldProps) {
  return (
    <div className="field">
      <label htmlFor="instruction">
        {label} {optional && <span className="optional">{optional}</span>}
      </label>
      <textarea
        id="instruction"
        rows={rows}
        maxLength={1000}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
      />
      <div className="examples" aria-label="Examples">
        {examples.map((example) => (
          <button type="button" key={example} className="chip" onClick={() => onChange(example)}>
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}

interface ColumnPickerProps {
  columns: Column[];
  selected: string[];
  hint: string;
  onChange: (selected: string[]) => void;
}

function ColumnPicker({ columns, selected, hint, onChange }: ColumnPickerProps) {
  function toggle(name: string) {
    // Keep the selection in the table's column order.
    onChange(columns.map((c) => c.name).filter((c) => (c === name ? !selected.includes(name) : selected.includes(c))));
  }

  return (
    <fieldset className="field">
      <legend>Columns</legend>
      <div className="column-chips">
        {columns.map((column) => {
          const active = selected.includes(column.name);
          return (
            <button
              type="button"
              key={column.name}
              className={`chip chip--column${active ? " chip--active" : ""}`}
              aria-pressed={active}
              onClick={() => toggle(column.name)}
            >
              {column.name}
              <span className="chip__kind">{column.kind}</span>
            </button>
          );
        })}
      </div>
      <p className="hint">{selected.length > 0 ? `Only in ${selected.join(", ")}.` : hint}</p>
    </fieldset>
  );
}

function NeedsLlmHint({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <p className="hint hint--warning">This kind of step needs a language model, and none is configured on this server.</p>
  );
}
