import { useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { Column, RowsPage } from "../api/types";
import { plural } from "../utils/text";
import { ErrorBanner } from "./ErrorBanner";
import { Spinner } from "./Spinner";

const PAGE_SIZES = [25, 50, 100, 200];

interface Props {
  datasetId: string;
  /** Changes whenever a step is applied or undone, which reloads the page. */
  version: number;
  columns: Column[];
}

export function DataTable({ datasetId, version, columns }: Props) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [data, setData] = useState<RowsPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    api
      .rows(datasetId, page, pageSize, controller.signal)
      .then((result) => {
        setData(result);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        setError(caught instanceof ApiError ? caught : new Error("The rows could not be loaded."));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [datasetId, version, page, pageSize]);

  const offset = data ? (data.page - 1) * data.page_size : 0;

  return (
    <section className="card table-card" aria-labelledby="table-title">
      <div className="card__header">
        <h2 id="table-title">Data</h2>
        <div className="table-card__status">
          {loading && (
            <span className="hint">
              <Spinner /> Loading…
            </span>
          )}
          {data?.changed_cells && (
            <span className="legend">
              <span className="legend__swatch" aria-hidden="true" /> Changed by the latest step
            </span>
          )}
        </div>
      </div>

      {error && <ErrorBanner error={error} />}

      <div className="table-scroll" aria-busy={loading}>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col" className="data-table__index">
                #
              </th>
              {columns.map((column) => (
                <th scope="col" key={column.name}>
                  <span className="data-table__name">{column.name}</span>
                  <span className="kind">{column.kind}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data?.rows.map((row, rowIndex) => {
              const changed = data.changed_cells?.[rowIndex] ?? [];
              return (
                <tr key={offset + rowIndex}>
                  <th scope="row" className="data-table__index">
                    {(offset + rowIndex + 1).toLocaleString("en-AU")}
                  </th>
                  {row.map((cell, cellIndex) => {
                    const isChanged = changed.includes(cellIndex);
                    return (
                      <td
                        key={cellIndex}
                        className={isChanged ? "cell--changed" : undefined}
                        title={cell.length > 40 ? cell : undefined}
                      >
                        {cell === "" ? <span className="empty-value">—</span> : cell}
                        {isChanged && <span className="visually-hidden"> (changed)</span>}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {data && (
        <div className="pagination">
          <span className="hint">{plural(data.total_rows, "row")}</span>
          <div className="pagination__controls">
            <button type="button" className="button button--small" disabled={data.page <= 1} onClick={() => setPage(1)}>
              « First
            </button>
            <button
              type="button"
              className="button button--small"
              disabled={data.page <= 1}
              onClick={() => setPage(data.page - 1)}
            >
              ‹ Previous
            </button>
            <span>
              Page {data.page.toLocaleString("en-AU")} of {data.total_pages.toLocaleString("en-AU")}
            </span>
            <button
              type="button"
              className="button button--small"
              disabled={data.page >= data.total_pages}
              onClick={() => setPage(data.page + 1)}
            >
              Next ›
            </button>
            <button
              type="button"
              className="button button--small"
              disabled={data.page >= data.total_pages}
              onClick={() => setPage(data.total_pages)}
            >
              Last »
            </button>
          </div>
          <label className="pagination__size">
            Rows per page
            <select
              value={pageSize}
              onChange={(event) => {
                setPageSize(Number(event.target.value));
                setPage(1);
              }}
            >
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
    </section>
  );
}
