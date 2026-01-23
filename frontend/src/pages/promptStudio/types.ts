import type { PromptBlock, PromptPreset } from "../../types";

export type PresetDetails = { preset: PromptPreset; blocks: PromptBlock[] };

export type BlockDraft = {
  identifier: string;
  name: string;
  role: string;
  enabled: boolean;
  template: string;
  marker_key: string;
  triggers: string;
};

export type PromptStudioTask = { key: string; label: string };
