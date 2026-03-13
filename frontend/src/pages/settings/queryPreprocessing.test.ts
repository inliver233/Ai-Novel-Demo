import { describe, expect, it } from "vitest";

import type { ProjectSettings } from "../../types";
import { createDefaultSettingsForm } from "./models";
import {
  getQueryPreprocessErrorField,
  isSameQueryPreprocess,
  parseLineList,
  queryPreprocessFromBaseline,
  queryPreprocessFromForm,
  validateQueryPreprocess,
} from "./queryPreprocessing";

describe("settings/queryPreprocessing", () => {
  it("parses trimmed line lists without blanks", () => {
    expect(parseLineList(" foo \n\nbar\r\n baz ")).toEqual(["foo", "bar", "baz"]);
  });

  it("maps form state into a query preprocessing config", () => {
    const form = {
      ...createDefaultSettingsForm(),
      query_preprocessing_enabled: true,
      query_preprocessing_tags: "foo\nbar",
      query_preprocessing_exclusion_rules: "REMOVE",
      query_preprocessing_index_ref_enhance: true,
    };
    expect(queryPreprocessFromForm(form)).toEqual({
      enabled: true,
      tags: ["foo", "bar"],
      exclusion_rules: ["REMOVE"],
      index_ref_enhance: true,
    });
  });

  it("maps effective baseline settings and compares configs", () => {
    const settings = {
      query_preprocessing_effective: {
        enabled: true,
        tags: ["foo"],
        exclusion_rules: ["REMOVE"],
        index_ref_enhance: true,
      },
    } as ProjectSettings;
    const baseline = queryPreprocessFromBaseline(settings);
    expect(isSameQueryPreprocess(baseline, baseline)).toBe(true);
    expect(
      isSameQueryPreprocess(baseline, {
        ...baseline,
        tags: ["bar"],
      }),
    ).toBe(false);
  });

  it("validates limits and resolves the offending field", () => {
    const tooLongTag = "x".repeat(65);
    const error = validateQueryPreprocess({
      enabled: true,
      tags: [tooLongTag],
      exclusion_rules: [],
      index_ref_enhance: false,
    });
    expect(error).toBe("tag 过长（最多 64 字符）");
    expect(getQueryPreprocessErrorField(error)).toBe("tags");
    expect(getQueryPreprocessErrorField("exclusion_rule 过长（最多 256 字符）")).toBe("exclusion_rules");
  });
});
