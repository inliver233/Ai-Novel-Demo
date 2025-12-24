import { useCallback, useMemo, useState } from "react";

import { useProjectData } from "./useProjectData";
import { apiJson } from "../services/apiClient";
import { computeWizardProgress, type WizardProgress } from "../services/wizard";
import type { Chapter, Character, LLMPreset, LLMProfile, Outline, Project, ProjectSettings } from "../types";

type WizardLoaded = {
  project: Project;
  settings: ProjectSettings;
  characters: Character[];
  outline: Outline;
  chapters: Chapter[];
  llmPreset: LLMPreset;
  profiles: LLMProfile[];
};

const EMPTY_CHARACTERS: Character[] = [];
const EMPTY_CHAPTERS: Chapter[] = [];

export function useWizardProgress(projectId: string | undefined): {
  loading: boolean;
  progress: WizardProgress;
  refresh: () => Promise<void>;
  bumpLocal: () => void;
} {
  const [version, setVersion] = useState(0);

  const wizardQuery = useProjectData<WizardLoaded>(projectId, async (id) => {
    const [pRes, settingsRes, charsRes, outlineRes, presetRes, profilesRes] = await Promise.all([
      apiJson<{ project: Project }>(`/api/projects/${id}`),
      apiJson<{ settings: ProjectSettings }>(`/api/projects/${id}/settings`),
      apiJson<{ characters: Character[] }>(`/api/projects/${id}/characters`),
      apiJson<{ outline: Outline }>(`/api/projects/${id}/outline`),
      apiJson<{ llm_preset: LLMPreset }>(`/api/projects/${id}/llm_preset`),
      apiJson<{ profiles: LLMProfile[] }>(`/api/llm_profiles`),
    ]);
    const chaptersRes = await apiJson<{ chapters: Chapter[] }>(`/api/projects/${id}/chapters`);
    return {
      project: pRes.data.project,
      settings: settingsRes.data.settings,
      characters: charsRes.data.characters,
      outline: outlineRes.data.outline,
      chapters: chaptersRes.data.chapters,
      llmPreset: presetRes.data.llm_preset,
      profiles: profilesRes.data.profiles,
    };
  });

  const bumpLocal = useCallback(() => {
    setVersion((v) => v + 1);
  }, []);

  const progress = useMemo(() => {
    void version;
    const project = wizardQuery.data?.project ?? null;
    const selectedProfileId = project?.llm_profile_id ?? null;
    const profiles = wizardQuery.data?.profiles ?? [];
    const llmProfile = selectedProfileId ? (profiles.find((p) => p.id === selectedProfileId) ?? null) : null;
    return computeWizardProgress({
      project,
      settings: wizardQuery.data?.settings ?? null,
      characters: wizardQuery.data?.characters ?? EMPTY_CHARACTERS,
      outline: wizardQuery.data?.outline ?? null,
      chapters: wizardQuery.data?.chapters ?? EMPTY_CHAPTERS,
      llmPreset: wizardQuery.data?.llmPreset ?? null,
      llmProfile,
    });
  }, [version, wizardQuery.data]);

  return {
    loading: wizardQuery.loading,
    progress,
    refresh: wizardQuery.refresh,
    bumpLocal,
  };
}
