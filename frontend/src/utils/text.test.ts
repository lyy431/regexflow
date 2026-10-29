import { describe, expect, it } from "vitest";

import { applySpans, plural, segmentsFromSpans } from "./text";

describe("segmentsFromSpans", () => {
  it("splits text into plain and matched parts", () => {
    expect(segmentsFromSpans("a1b22", [[1, 2], [3, 5]])).toEqual([
      { text: "a", matched: false },
      { text: "1", matched: true },
      { text: "b", matched: false },
      { text: "22", matched: true },
    ]);
  });

  it("counts code points like Python, so emoji do not shift the spans", () => {
    expect(segmentsFromSpans("😀 id 42", [[5, 7]]).at(-1)).toEqual({ text: "42", matched: true });
  });
});

describe("applySpans", () => {
  it("inserts the replacement literally", () => {
    expect(applySpans("call 0412 345 678 now", [[5, 17]], "$1 [phone]")).toBe("call $1 [phone] now");
  });

  it("can remove the matches", () => {
    expect(applySpans("URGENT: call", [[0, 6]], "")).toBe(": call");
  });
});

describe("plural", () => {
  it("formats counts", () => {
    expect(plural(1, "row")).toBe("1 row");
    expect(plural(1234, "match", "matches")).toBe("1,234 matches");
  });
});
