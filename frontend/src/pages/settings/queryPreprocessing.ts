import type { ProjectSettings, QueryPreprocessingConfig } from "../../types";

import type { SettingsForm } from "./models";

export function parseLineList(raw: string): string[] {
  return (raw || "")
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean);
}

export function queryPreprocessFromForm(form: SettingsForm): QueryPreprocessingConfig {
  return {
    enabled: Boolean(form.query_preprocessing_enabled),
    tags: parseLineList(form.query_preprocessing_tags),
    exclusion_rules: parseLineList(form.query_preprocessing_exclusion_rules),
    index_ref_enhance: Boolean(form.query_preprocessing_index_ref_enhance),
  };
}

export function queryPreprocessFromBaseline(settings: ProjectSettings): QueryPreprocessingConfig {
  const cfg = settings.query_preprocessing_effective;
  return {
    enabled: Boolean(cfg?.enabled),
    tags: Array.isArray(cfg?.tags) ? cfg.tags.map((value) => String(value)) : [],
    exclusion_rules: Array.isArray(cfg?.exclusion_rules) ? cfg.exclusion_rules.map((value) => String(value)) : [],
    index_ref_enhance: Boolean(cfg?.index_ref_enhance),
  };
}

export function isSameStringList(left: string[], right: string[]): boolean {
  if (left.length !== right.length) return false;
  for (let i = 0; i < left.length; i++) {
    if (left[i] !== right[i]) return false;
  }
  return true;
}

export function isSameQueryPreprocess(left: QueryPreprocessingConfig, right: QueryPreprocessingConfig): boolean {
  return (
    Boolean(left.enabled) === Boolean(right.enabled) &&
    Boolean(left.index_ref_enhance) === Boolean(right.index_ref_enhance) &&
    isSameStringList(left.tags ?? [], right.tags ?? []) &&
    isSameStringList(left.exclusion_rules ?? [], right.exclusion_rules ?? [])
  );
}

export function validateQueryPreprocess(config: QueryPreprocessingConfig): string | null {
  if ((config.tags ?? []).length > 50) return "tags 最多 50 条（每行一条）";
  for (const tag of config.tags ?? []) {
    if (!tag.trim()) return "tags 不能包含空行";
    if (tag.length > 64) return "tag 过长（最多 64 字符）";
  }
  if ((config.exclusion_rules ?? []).length > 50) return "exclusion_rules 最多 50 条（每行一条）";
  for (const rule of config.exclusion_rules ?? []) {
    if (!rule.trim()) return "exclusion_rules 不能包含空行";
    if (rule.length > 256) return "exclusion_rule 过长（最多 256 字符）";
  }
  return null;
}

export function getQueryPreprocessErrorField(error: string | null): "tags" | "exclusion_rules" | null {
  if (!error) return null;
  if (error.startsWith("tags") || error.startsWith("tag")) return "tags";
  if (error.startsWith("exclusion_rule") || error.startsWith("exclusion_rules")) return "exclusion_rules";
  return null;
}
