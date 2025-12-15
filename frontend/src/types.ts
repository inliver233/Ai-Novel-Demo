export type LLMProvider = "openai" | "openai_compatible" | "anthropic" | "gemini";

export type ChapterStatus = "planned" | "drafting" | "done";

export interface Project {
  id: string;
  owner_user_id: string;
  name: string;
  genre?: string | null;
  logline?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectSettings {
  project_id: string;
  world_setting: string;
  style_guide: string;
  constraints: string;
}

export interface Character {
  id: string;
  project_id: string;
  name: string;
  role?: string | null;
  profile?: string | null;
  notes?: string | null;
  updated_at: string;
}

export interface Outline {
  project_id: string;
  content_md: string;
  updated_at: string;
}

export interface Chapter {
  id: string;
  project_id: string;
  number: number;
  title?: string | null;
  plan?: string | null;
  content_md?: string | null;
  summary?: string | null;
  status: ChapterStatus;
  updated_at: string;
}

export interface PromptTemplate {
  type: "outline_generate" | "chapter_generate";
  system_template: string;
  user_template: string;
  updated_at?: string | null;
}

export interface LLMPreset {
  project_id: string;
  provider: LLMProvider;
  base_url?: string | null;
  model: string;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
  top_k?: number | null;
  stop: string[];
  timeout_seconds?: number | null;
  extra: Record<string, unknown>;
}

