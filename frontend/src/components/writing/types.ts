export type CreateChapterForm = {
  number: number;
  title: string;
  plan: string;
};

export type GenerateForm = {
  instruction: string;
  target_word_count: number;
  stream: boolean;
  plan_first: boolean;
  post_edit: boolean;
  context: {
    include_world_setting: boolean;
    include_style_guide: boolean;
    include_constraints: boolean;
    include_outline: boolean;
    character_ids: string[];
    previous_chapter: "none" | "summary" | "content";
  };
};

export type GenerationRun = {
  id: string;
  project_id: string;
  actor_user_id?: string | null;
  chapter_id?: string | null;
  type: string;
  provider?: string | null;
  model?: string | null;
  request_id?: string | null;
  prompt_system?: string | null;
  prompt_user?: string | null;
  params?: unknown;
  output_text?: string | null;
  error?: unknown;
  created_at: string;
};
