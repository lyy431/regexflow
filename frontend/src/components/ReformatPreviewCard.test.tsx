import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ReformatPreview } from "../api/types";
import { ReformatPreviewCard } from "./ReformatPreviewCard";

const PREVIEW: ReformatPreview = {
  kind: "reformat",
  pattern: "(?P<d>\\d{2})/(?P<m>\\d{2})/(?P<y>\\d{4})",
  flags: [],
  template: "\\g<y>-\\g<m>-\\g<d>",
  columns: ["Joined"],
  explanation: "Rewrites DD/MM/YYYY dates as YYYY-MM-DD.",
  source: "groq:openai/gpt-oss-120b",
  cached: false,
  stats: { matches: 2, cells_changed: 2, rows_affected: 2, matches_by_column: { Joined: 2 } },
  samples: [{ row: 0, column: "Joined", before: "31/01/2024", after: "2024-01-31", spans: [[0, 10]] }],
};

function renderCard() {
  const handlers = { onApply: vi.fn(), onRerun: vi.fn(), onDiscard: vi.fn() };
  render(<ReformatPreviewCard preview={PREVIEW} instruction="dates to ISO" busy={null} {...handlers} />);
  return handlers;
}

describe("ReformatPreviewCard", () => {
  it("shows the rewritten values and applies the step", async () => {
    const { onApply } = renderCard();

    expect(screen.getByText("2024-01-31")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Apply step" }));

    expect(onApply).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "reformat", template: "\\g<y>-\\g<m>-\\g<d>", columns: ["Joined"] }),
    );
  });

  it("requires an updated preview after the template is edited", async () => {
    const { onRerun } = renderCard();

    await userEvent.clear(screen.getByLabelText("Rewrite as"));
    await userEvent.type(screen.getByLabelText("Rewrite as"), "year {{y}");

    expect(screen.getByRole("button", { name: "Apply step" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Update preview" }));
    expect(onRerun).toHaveBeenCalledWith(expect.objectContaining({ kind: "reformat", template: "year {y}" }));
  });
});
