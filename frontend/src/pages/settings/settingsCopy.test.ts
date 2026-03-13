import { describe, expect, it } from "vitest";

import { formatBinaryStatus, SETTINGS_COPY } from "./settingsCopy";

describe("settingsCopy", () => {
  it("formats binary status consistently", () => {
    expect(formatBinaryStatus(true)).toBe("enabled");
    expect(formatBinaryStatus(false)).toBe("disabled");
  });

  it("keeps the feature-default status string stable", () => {
    expect(SETTINGS_COPY.featureDefaults.status(true)).toContain("memory_injection_default=enabled");
  });

  it("keeps the settings vector save-before-test toast explicit", () => {
    expect(SETTINGS_COPY.vectorRag.saveBeforeTestToast).toContain("保存设置");
  });
});
