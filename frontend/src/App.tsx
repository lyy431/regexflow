import { useEffect, useState } from "react";

import { api, ApiError } from "./api/client";
import type { Dataset, ServerInfo } from "./api/types";
import { Spinner } from "./components/Spinner";
import { UploadPanel } from "./components/UploadPanel";
import { Workspace } from "./components/Workspace";

// The open dataset's id is kept in the URL, so refreshing the page keeps your work.
const DATASET_PARAM = "dataset";

function datasetIdFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get(DATASET_PARAM);
}

function setDatasetIdInUrl(id: string | null) {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set(DATASET_PARAM, id);
  else url.searchParams.delete(DATASET_PARAM);
  window.history.replaceState(null, "", url);
}

export default function App() {
  const [serverInfo, setServerInfo] = useState<ServerInfo | null>(null);
  const [serverDown, setServerDown] = useState(false);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [restoring, setRestoring] = useState(() => datasetIdFromUrl() !== null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    api
      .health()
      .then(setServerInfo)
      .catch(() => setServerDown(true));
  }, []);

  useEffect(() => {
    const id = datasetIdFromUrl();
    if (!id) return;
    api
      .getDataset(id)
      .then(setDataset)
      .catch((error: unknown) => {
        setNotice(error instanceof ApiError ? error.message : "Your previous dataset could not be reopened.");
        setDatasetIdInUrl(null);
      })
      .finally(() => setRestoring(false));
  }, []);

  function openDataset(next: Dataset | null) {
    setDataset(next);
    setNotice(null);
    setDatasetIdInUrl(next?.id ?? null);
  }

  return (
    <div className="app">
      <header className="app-header">
        <a className="brand" href="/" aria-label="RegexFlow home">
          <span className="brand__mark" aria-hidden="true" />
          <span className="brand__name">RegexFlow</span>
        </a>
        <span className="app-header__tagline">Find and replace with plain English</span>
      </header>

      <main className="app-main">
        {restoring ? (
          <p className="loading">
            <Spinner /> Reopening your dataset…
          </p>
        ) : dataset ? (
          <Workspace
            dataset={dataset}
            serverInfo={serverInfo}
            onDatasetChange={setDataset}
            onClose={() => openDataset(null)}
          />
        ) : (
          <UploadPanel serverInfo={serverInfo} notice={notice} onUploaded={openDataset} />
        )}
      </main>

      <footer className="app-footer">
        <span>
          {serverDown
            ? "The server is not responding."
            : !serverInfo
              ? "Connecting to the server…"
              : serverInfo.llm_providers.length > 0
                ? `Language models: ${serverInfo.llm_providers.join(" → ")}`
                : "No language model configured: write regular expressions by hand."}
        </span>
        <span>Django · React · free-tier LLM APIs</span>
      </footer>
    </div>
  );
}
