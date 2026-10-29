import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Column } from "../api/types";
import { EXAMPLES, TransformPanel } from "./TransformPanel";

const COLUMNS: Column[] = [
  { name: "Name", kind: "text" },
  { name: "Email", kind: "text" },
  { name: "State", kind: "text" },
];

function renderPanel(llmAvailable: boolean | null = true) {
  const onPreview = vi.fn();
  render(<TransformPanel columns={COLUMNS} busy={false} llmAvailable={llmAvailable} onPreview={onPreview} />);
  return onPreview;
}

describe("TransformPanel", () => {
  it("sends the description, leaving the replacement to the instruction when blank", async () => {
    const onPreview = renderPanel();

    await userEvent.click(screen.getByRole("button", { name: EXAMPLES.regex_replace[0] }));
    await userEvent.click(screen.getByRole("button", { name: /Email/ }));
    await userEvent.click(screen.getByRole("button", { name: "Preview changes" }));

    expect(onPreview).toHaveBeenCalledWith({
      kind: "regex_replace",
      instruction: EXAMPLES.regex_replace[0],
      replacement: null,
      columns: ["Email"],
    });
  });

  it("switches to writing a regex when no language model is configured", async () => {
    const onPreview = renderPanel(false);

    expect(screen.getByRole("button", { name: "Describe it" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Regular expression/), "Doe");
    await userEvent.type(screen.getByLabelText(/Replace with/), "Roe");
    await userEvent.click(screen.getByRole("button", { name: "Preview changes" }));

    expect(onPreview).toHaveBeenCalledWith({
      kind: "regex_replace",
      pattern: "Doe",
      flags: [],
      replacement: "Roe",
      columns: [],
    });
  });

  it("asks to standardise a format", async () => {
    const onPreview = renderPanel();

    await userEvent.click(screen.getByRole("tab", { name: "Standardise format" }));
    await userEvent.click(screen.getByRole("button", { name: EXAMPLES.reformat[0] }));
    await userEvent.click(screen.getByRole("button", { name: "Preview changes" }));

    expect(onPreview).toHaveBeenCalledWith({ kind: "reformat", instruction: EXAMPLES.reformat[0], columns: [] });
  });

  it("asks to normalise the values of one column", async () => {
    const onPreview = renderPanel();

    await userEvent.click(screen.getByRole("tab", { name: "Normalise values" }));
    const preview = screen.getByRole("button", { name: "Preview changes" });
    expect(preview).toBeDisabled(); // a column is required
    await userEvent.selectOptions(screen.getByLabelText("Column to clean up"), "State");
    await userEvent.click(preview);

    expect(onPreview).toHaveBeenCalledWith({ kind: "normalize_values", column: "State", instruction: "" });
  });

  it("disables the language-model steps when none is configured", async () => {
    renderPanel(false);

    await userEvent.click(screen.getByRole("tab", { name: "Standardise format" }));

    expect(screen.getByText(/needs a language model/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview changes" })).toBeDisabled();
  });
});
