import { useState } from "react";

import { api, ApiError } from "../api/client";
import type { ApplyRequest, Dataset, Preview, ServerInfo, StepRequest } from "../api/types";
import { DataTable } from "./DataTable";
import { DatasetHeader } from "./DatasetHeader";
import { ErrorBanner } from "./ErrorBanner";
import { NormalizePreviewCard } from "./NormalizePreviewCard";
import { PreviewCard } from "./PreviewCard";
import type { PreviewBusy } from "./PreviewParts";
import { ReformatPreviewCard } from "./ReformatPreviewCard";
import { StepsList } from "./StepsList";
import { TransformPanel } from "./TransformPanel";

type Busy = "preview" | "apply" | "undo" | null;

interface PreviewState {
  id: number; // remounts the card, resetting its edits, for every new preview
  instruction: string;
  result: Preview;
}

interface Props {
  dataset: Dataset;
  serverInfo: ServerInfo | null;
  onDatasetChange: (dataset: Dataset) => void;
  onClose: () => void;
}

const GONE = new Set(["dataset_not_found", "dataset_expired"]);

export function Workspace({ dataset, serverInfo, onDatasetChange, onClose }: Props) {
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<Error | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const llmAvailable = serverInfo ? serverInfo.llm_providers.length > 0 : null;

  async function run<T>(kind: Exclude<Busy, null>, action: () => Promise<T>): Promise<T | undefined> {
    setBusy(kind);
    setError(null);
    setMessage(null);
    try {
      return await action();
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error("Something went wrong."));
      return undefined;
    } finally {
      setBusy(null);
    }
  }

  async function requestPreview(request: StepRequest) {
    const result = await run("preview", () => api.preview(dataset.id, request));
    if (result) {
      setPreview((current) => ({ id: (current?.id ?? 0) + 1, instruction: request.instruction ?? "", result }));
    }
  }

  function renderPreview({ id, instruction, result }: PreviewState) {
    const cardBusy: PreviewBusy = busy === "preview" || busy === "apply" ? busy : null;
    const shared = { key: id, instruction, busy: cardBusy, onApply: applyStep, onDiscard: () => setPreview(null) };
    switch (result.kind) {
      case "regex_replace":
        return <PreviewCard {...shared} preview={result} onRerun={requestPreview} />;
      case "reformat":
        return <ReformatPreviewCard {...shared} preview={result} onRerun={requestPreview} />;
      case "normalize_values":
        return <NormalizePreviewCard {...shared} preview={result} />;
    }
  }

  async function applyStep(request: ApplyRequest) {
    const updated = await run("apply", () => api.apply(dataset.id, request));
    if (updated) {
      onDatasetChange(updated);
      setPreview(null);
      setMessage(`Step ${updated.current_version} applied. Changed cells are highlighted in the table.`);
    }
  }

  async function undoStep() {
    const updated = await run("undo", () => api.undo(dataset.id));
    if (updated) {
      onDatasetChange(updated);
      setPreview(null); // it was computed against the version that was just undone
      setMessage("The last step was undone.");
    }
  }

  const gone = error instanceof ApiError && GONE.has(error.code);

  return (
    <div className="workspace">
      <DatasetHeader dataset={dataset} onClose={onClose} />
      <div className="workspace__grid">
        <div className="workspace__side">
          <TransformPanel
            columns={dataset.columns}
            busy={busy === "preview"}
            llmAvailable={llmAvailable}
            onPreview={requestPreview}
          />
          {error && (
            <ErrorBanner
              error={error}
              onDismiss={() => setError(null)}
              action={gone ? { label: "Upload again", onClick: onClose } : undefined}
            />
          )}
          {message && (
            <div className="banner banner--success" role="status">
              {message}
            </div>
          )}
          {preview && renderPreview(preview)}
          <StepsList
            steps={dataset.transformations}
            undoing={busy === "undo"}
            disabled={busy !== null}
            onUndo={undoStep}
          />
        </div>
        <DataTable datasetId={dataset.id} version={dataset.current_version} columns={dataset.columns} />
      </div>
    </div>
  );
}
