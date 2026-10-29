import { api } from "../api/client";
import type { Dataset } from "../api/types";
import { plural } from "../utils/text";

interface Props {
  dataset: Dataset;
  onClose: () => void;
}

export function DatasetHeader({ dataset, onClose }: Props) {
  const steps = dataset.transformations.length;
  return (
    <div className="dataset-header">
      <div>
        <h1 className="dataset-header__name">{dataset.name}</h1>
        <p className="dataset-header__meta">
          {plural(dataset.row_count, "row")} · {plural(dataset.columns.length, "column")} ·{" "}
          {steps === 0 ? "original data" : `${plural(steps, "step")} applied`}
        </p>
      </div>
      <div className="dataset-header__actions">
        <a className="button" href={api.exportUrl(dataset.id, "csv")} download>
          Download CSV
        </a>
        <a className="button" href={api.exportUrl(dataset.id, "xlsx")} download>
          Download Excel
        </a>
        <button type="button" className="button button--ghost" onClick={onClose}>
          Upload another file
        </button>
      </div>
    </div>
  );
}
