import type { Transformation } from "../api/types";
import { plural } from "../utils/text";
import { Spinner } from "./Spinner";

interface Props {
  steps: Transformation[];
  undoing: boolean;
  disabled: boolean;
  onUndo: () => void;
}

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
        <p className="hint">Applied replacements appear here in order. You can undo them one at a time.</p>
      ) : (
        <ol className="steps__list">
          {steps.map((step) => (
            <li key={step.id} className="step">
              <div className="step__title">{step.instruction || "Hand-written regular expression"}</div>
              <code className="step__pattern">{step.params.pattern}</code>
              <div className="step__meta">
                {step.params.replacement === "" ? "Removed" : <>→ “{step.params.replacement}”</>} in{" "}
                {step.params.columns.join(", ")} · {plural(step.stats.cells_changed, "cell")} changed
                {step.source && step.source !== "manual" ? ` · ${step.source}` : ""}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
