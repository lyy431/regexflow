import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { FindReplacePreview } from "../api/types";
import { PreviewCard } from "./PreviewCard";

function makePreview(overrides: Partial<FindReplacePreview> = {}): FindReplacePreview {
  return {
    kind: "regex_replace",
    pattern: "\\b\\S+@\\S+\\b",
    flags: [],
    columns: ["Email"],
    replacement: "REDACTED",
    explanation: "Matches email addresses.",
    source: "gemini:gemini-3.1-flash-lite",
    cached: false,
    stats: { matches: 1, cells_changed: 1, rows_affected: 1, matches_by_column: { Email: 1 } },
    samples: [{ row: 0, column: "Email", before: "mail john@example.com", after: "mail REDACTED", spans: [[5, 21]] }],
    ...overrides,
  };
}

function renderCard(preview: FindReplacePreview) {
  const handlers = { onApply: vi.fn(), onRerun: vi.fn(), onDiscard: vi.fn() };
  render(<PreviewCard preview={preview} instruction="hide emails" busy={null} {...handlers} />);
  return handlers;
}

describe("PreviewCard", () => {
  it("applies the previewed pattern with the replacement", async () => {
    const { onApply } = renderCard(makePreview());

    await userEvent.click(screen.getByRole("button", { name: "Apply step" }));

    expect(onApply).toHaveBeenCalledWith({
      kind: "regex_replace",
      instruction: "hide emails",
      pattern: "\\b\\S+@\\S+\\b",
      flags: [],
      replacement: "REDACTED",
      columns: ["Email"],
      explanation: "Matches email addresses.",
      source: "gemini:gemini-3.1-flash-lite",
    });
  });

  it("asks for a replacement when none was given and updates the examples as you type", async () => {
    renderCard(makePreview({ replacement: null }));
    const apply = screen.getByRole("button", { name: "Apply step" });
    expect(apply).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Replace with"), "HIDDEN");

    expect(apply).toBeEnabled();
    expect(screen.getByText("HIDDEN", { selector: "ins" })).toBeInTheDocument();
  });

  it("requires an updated preview after the pattern is edited", async () => {
    const { onRerun } = renderCard(makePreview());

    await userEvent.type(screen.getByLabelText("Regular expression"), "x");

    expect(screen.getByRole("button", { name: "Apply step" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Update preview" }));
    expect(onRerun).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "regex_replace", pattern: "\\b\\S+@\\S+\\bx", replacement: "REDACTED" }),
    );
  });

  it("cannot apply a pattern that matched nothing", () => {
    renderCard(
      makePreview({ stats: { matches: 0, cells_changed: 0, rows_affected: 0, matches_by_column: {} }, samples: [] }),
    );
    expect(screen.getByText(/No matches/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply step" })).toBeDisabled();
  });
});
