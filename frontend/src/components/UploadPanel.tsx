import { useRef, useState, type DragEvent } from "react";

import { api } from "../api/client";
import type { Dataset, ServerInfo } from "../api/types";
import { SAMPLE_CSV, SAMPLE_FILE_NAME } from "../sampleData";
import { ErrorBanner } from "./ErrorBanner";
import { Spinner } from "./Spinner";

const EXTENSIONS = [".csv", ".tsv", ".xlsx", ".xlsm", ".xls"];

interface Props {
  serverInfo: ServerInfo | null;
  notice: string | null;
  onUploaded: (dataset: Dataset) => void;
}

function checkFile(file: File, maxMb: number | undefined): string | null {
  const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (!EXTENSIONS.includes(extension)) return `“${file.name}” is not a CSV or Excel file.`;
  if (maxMb && file.size > maxMb * 1024 * 1024) return `“${file.name}” is larger than ${maxMb} MB.`;
  return null;
}

export function UploadPanel({ serverInfo, notice, onUploaded }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const maxMb = serverInfo?.max_upload_size_mb;

  async function upload(file: File) {
    const problem = checkFile(file, maxMb);
    if (problem) {
      setError(new Error(problem));
      return;
    }
    setError(null);
    setProgress(0);
    try {
      onUploaded(await api.upload(file, setProgress));
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error("The upload failed."));
    } finally {
      setProgress(null);
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file && progress === null) void upload(file);
  }

  return (
    <section className="upload">
      <div className="upload__intro">
        <h1>Find and replace in spreadsheets, in plain English</h1>
        <p>
          Upload a CSV or Excel file and describe what to find, such as “email addresses” or “Australian mobile
          numbers”. A language model writes the regular expression, and you preview every change before applying it.
        </p>
      </div>

      {notice && <div className="banner banner--info">{notice}</div>}

      <div
        className={`dropzone${dragging ? " dropzone--active" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept={EXTENSIONS.join(",")}
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void upload(file);
          }}
        />
        {progress === null ? (
          <>
            <p className="dropzone__title">Drop a file here</p>
            <p className="dropzone__hint">CSV, TSV, XLSX or XLS{maxMb ? ` · up to ${maxMb} MB` : ""}</p>
            <div className="dropzone__actions">
              <button type="button" className="button button--primary" onClick={() => inputRef.current?.click()}>
                Choose a file
              </button>
              <button
                type="button"
                className="button"
                onClick={() => void upload(new File([SAMPLE_CSV], SAMPLE_FILE_NAME, { type: "text/csv" }))}
              >
                Try the sample file
              </button>
            </div>
          </>
        ) : (
          <div className="dropzone__progress" role="status">
            <p>
              <Spinner /> {progress < 1 ? `Uploading… ${Math.round(progress * 100)}%` : "Reading your file…"}
            </p>
            <progress max={1} value={progress} />
          </div>
        )}
      </div>

      {error && <ErrorBanner error={error} onDismiss={() => setError(null)} />}

      <p className="upload__privacy">
        Only your description and the column names are sent to the language model; cell values stay on the server.
        {serverInfo && serverInfo.dataset_ttl_hours > 0
          ? ` Uploaded files are deleted after ${serverInfo.dataset_ttl_hours} hours without activity.`
          : ""}
      </p>
    </section>
  );
}
