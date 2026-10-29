import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Column } from "../api/types";
import { EXAMPLES, TransformPanel } from "./TransformPanel";

const COLUMNS: Column[] = [
  { name: "Name", kind: "text" },
  { name: "Email", kind: "text" },
];

describe("TransformPanel", () => {
  it("sends the description, leaving the replacement to the instruction when blank", async () => {
    const onPreview = vi.fn();
    render(<TransformPanel columns={COLUMNS} busy={false} llmAvailable onPreview={onPreview} />);

    await userEvent.click(screen.getByRole("button", { name: EXAMPLES[0] }));
    await userEvent.click(screen.getByRole("button", { name: /Email/ }));
    await userEvent.click(screen.getByRole("button", { name: "Preview changes" }));

    expect(onPreview).toHaveBeenCalledWith({ instruction: EXAMPLES[0], replacement: null, columns: ["Email"] });
  });

  it("switches to writing a regex when no language model is configured", async () => {
    const onPreview = vi.fn();
    render(<TransformPanel columns={COLUMNS} busy={false} llmAvailable={false} onPreview={onPreview} />);

    expect(screen.getByRole("button", { name: "Describe it" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Regular expression/), "Doe");
    await userEvent.type(screen.getByLabelText(/Replace with/), "Roe");
    await userEvent.click(screen.getByRole("button", { name: "Preview changes" }));

    expect(onPreview).toHaveBeenCalledWith({ pattern: "Doe", flags: [], replacement: "Roe", columns: [] });
  });
});
