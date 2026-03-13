import { describe, expect, it } from "vitest";

import { formatWorldBookActionError } from "./worldbookCopy";

describe("worldbookCopy", () => {
  it("formats single-action API errors consistently", () => {
    expect(formatWorldBookActionError("导入失败", { message: "bad payload", code: "INVALID_JSON" })).toBe(
      "导入失败：bad payload (INVALID_JSON)",
    );
  });

  it("includes selected-count context for bulk failures", () => {
    expect(
      formatWorldBookActionError("批量更新失败", { message: "write locked", code: "SQLITE_BUSY" }, { count: 3 }),
    ).toBe("批量更新失败（3条）：write locked (SQLITE_BUSY)");
  });
});
