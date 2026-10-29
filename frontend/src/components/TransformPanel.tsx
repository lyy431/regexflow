import { useState, type FormEvent, type KeyboardEvent } from "react";

import type { Column, RegexFlag, ReplacementRequest } from "../api/types";
import { FlagToggles } from "./FlagToggles";
import { Spinner } from "./Spinner";

export const EXAMPLES = [
  "Find email addresses and replace them with 'REDACTED'",
  "Mask Australian mobile numbers with '[phone]'",
  "Replace website links with '[link]'",
  "Remove the word 'urgent' in any capitalisation",
];

type Mode = "describe" | "regex";

interface Props {
  columns: Column[];
  busy: boolean;
  /** null while unknown; false when the server has no LLM configured. */
  llmAvailable: boolean | null;
  onPreview: (request: ReplacementRequest) => void;
}

export function TransformPanel({ columns, busy, llmAvailable, onPreview }: Props) {
  const [chosenMode, setChosenMode] = useState<Mode>("describe");
  const [instruction, setInstruction] = useState("");
  const [pattern, setPattern] = useState("");
  const [flags, setFlags] = useState<RegexFlag[]>([]);
  const [replacement, setReplacement] = useState("");
  const [selected, setSelected] = useState<string[]>([]);

  const mode: Mode = llmAvailable === false ? "regex" : chosenMode;
  const canSubmit = !busy && (mode === "describe" ? instruction.trim() !== "" : pattern !== "");

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!canSubmit) return;
    // A blank field means "not specified": the instruction may say what to use.
    const shared = { replacement: replacement === "" ? null : replacement, columns: selected };
    onPreview(mode === "describe" ? { instruction: instruction.trim(), ...shared } : { pattern, flags, ...shared });
  }

  function submitOnCtrlEnter(event: KeyboardEvent) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) submit();
  }

  function toggleColumn(name: string) {
    setSelected((current) =>
      current.includes(name) ? current.filter((c) => c !== name) : columns.map((c) => c.name).filter((c) => c === name || current.includes(c)),
    );
  }

  return (
    <form className="card transform" onSubmit={submit}>
      <div className="card__header">
        <h2>New step</h2>
        <div className="segmented" role="group" aria-label="How to define the pattern">
          <button
            type="button"
            aria-pressed={mode === "describe"}
            disabled={llmAvailable === false}
            onClick={() => setChosenMode("describe")}
          >
            Describe it
          </button>
          <button type="button" aria-pressed={mode === "regex"} onClick={() => setChosenMode("regex")}>
            Write a regex
          </button>
        </div>
      </div>

      {llmAvailable === false && (
        <p className="hint hint--warning">
          No language model is configured on this server, so write the regular expression yourself.
        </p>
      )}

      {mode === "describe" ? (
        <div className="field">
          <label htmlFor="instruction">What should be found?</label>
          <textarea
            id="instruction"
            rows={3}
            maxLength={1000}
            value={instruction}
            placeholder="e.g. Find email addresses in the Email column and replace them with 'REDACTED'"
            onChange={(event) => setInstruction(event.target.value)}
            onKeyDown={submitOnCtrlEnter}
          />
          <div className="examples" aria-label="Example descriptions">
            {EXAMPLES.map((example) => (
              <button type="button" key={example} className="chip" onClick={() => setInstruction(example)}>
                {example}
              </button>
            ))}
          </div>
        </div>
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
                onClick={() => toggleColumn(column.name)}
              >
                {column.name}
                <span className="chip__kind">{column.kind}</span>
              </button>
            );
          })}
        </div>
        <p className="hint">
          {selected.length > 0
            ? `Only in ${selected.join(", ")}.`
            : mode === "describe"
              ? "None selected: the columns your description names, otherwise every text column."
              : "None selected: every text column."}
        </p>
      </fieldset>

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
