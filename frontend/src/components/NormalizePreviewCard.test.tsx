import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { NormalizePreview } from "../api/types";
import { NormalizePreviewCard } from "./NormalizePreviewCard";

function makePreview(overrides: Partial<NormalizePreview> = {}): NormalizePreview {
  return {
    kind: "normalize_values",
    column: "State",
    columns: ["State"],
    mapping: [
      { from: "Victoria", to: "VIC", count: 4 },
      { from: "nsw", to: "NSW", count: 2 },
      { from: "Qld", to: "QLD", count: 1 },
    ],
    explanation: "Uses the official abbreviations.",
    source: "gemini:gemini-3.1-flash-lite",
    cached: false,
    stats: { matches: 7, cells_changed: 7, rows_affected: 7, matches_by_column: { State: 7 } },
    samples: [],
    ...overrides,
  };
}

function renderCard(preview: NormalizePreview) {
  const onApply = vi.fn();
  render(<NormalizePreviewCard preview={preview} instruction="abbreviations" busy={null} onApply={onApply} onDiscard={vi.fn()} />);
  return onApply;
}

describe("NormalizePreviewCard", () => {
  it("applies the mapping as the user edited it", async () => {
    const onApply = renderCard(makePreview());
    expect(screen.getByText("3 values will be replaced in 7 cells.")).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText("Change “Qld”"));
    await userEvent.clear(screen.getByLabelText("New value for “nsw”"));
    await userEvent.type(screen.getByLabelText("New value for “nsw”"), "New South Wales");

    expect(screen.getByText("2 values will be replaced in 6 cells.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Apply step" }));
    expect(onApply).toHaveBeenCalledWith({
      kind: "normalize_values",
      column: "State",
      instruction: "abbreviations",
      mapping: { Victoria: "VIC", nsw: "New South Wales" },
      explanation: "Uses the official abbreviations.",
      source: "gemini:gemini-3.1-flash-lite",
    });
  });

  it("says when every value is already consistent", () => {
    renderCard(makePreview({ mapping: [], stats: { matches: 0, cells_changed: 0, rows_affected: 0, matches_by_column: {} } }));

    expect(screen.getByText(/already look consistent/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply step" })).toBeDisabled();
  });
});
