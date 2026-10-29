import type { Transformation } from "../api/types";
import { plural } from "../utils/text";
import { Spinner } from "./Spinner";

interface Props {
  steps: Transformation[];
  undoing: boolean;
  disabled: boolean;
  onUndo: () => void;
}

const KIND_LABELS: Record<Transformation["kind"], string> = {
  regex_replace: "Find & replace",
  reformat: "Format",
  normalize_values: "Normalise",
};

export function StepsList({ steps, undoing, disabled, onUndo }: Props) {
  return (
    <section className="card steps" aria-labelledby="steps-title">
      <div className="card__header">
        <h2 id="steps-title">Steps</h2>
        {steps.length > 0 && (
          <button type="button" className="button button--small" onClick={onUndo} disabled={disabled}>
            {undoing ? (
              <>
                <Spinner /> Undoing…
              </>
            ) : (
              "Undo last step"
            )}
          </button>
        )}
      </div>
      {steps.length === 0 ? (
        <p className="hint">Applied steps appear here in order. You can undo them one at a time.</p>
      ) : (
        <ol className="steps__list">
          {steps.map((step) => (
            <li key={step.id} className="step">
              <div className="step__title">
                <span className="tag">{KIND_LABELS[step.kind]}</span> {step.instruction || defaultTitle(step)}
              </div>
              <StepDetails step={step} />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function defaultTitle(step: Transformation): string {
  switch (step.kind) {
    case "regex_replace":
      return "Hand-written regular expression";
    case "reformat":
      return "Hand-written format rewrite";
    case "normalize_values":
      return `Normalised values in ${step.params.column}`;
  }
}

function StepDetails({ step }: { step: Transformation }) {
  const changed = `${plural(step.stats.cells_changed, "cell")} changed`;
  const source = step.source && step.source !== "manual" ? ` · ${step.source}` : "";
  switch (step.kind) {
    case "regex_replace":
      return (
        <>
          <code className="step__pattern">{step.params.pattern}</code>
          <div className="step__meta">
            {step.params.replacement === "" ? "Removed" : <>→ “{step.params.replacement}”</>} in{" "}
            {step.params.columns.join(", ")} · {changed}
            {source}
          </div>
        </>
      );
    case "reformat":
      return (
        <>
          <code className="step__pattern">{step.params.pattern}</code>
          <div className="step__meta">
            → <code>{step.params.template}</code> in {step.params.columns.join(", ")} · {changed}
            {source}
          </div>
        </>
      );
    case "normalize_values": {
      const pairs = Object.entries(step.params.mapping);
      return (
        <div className="step__meta">
          {pairs
            .slice(0, 3)
            .map(([from, to]) => `${from} → ${to}`)
            .join(", ")}
          {pairs.length > 3 ? ` and ${pairs.length - 3} more` : ""} in {step.params.column} · {changed}
          {source}
        </div>
      );
    }
  }
}
