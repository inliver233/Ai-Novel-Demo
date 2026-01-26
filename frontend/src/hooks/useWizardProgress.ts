import { useCallback, useEffect, useRef, useState } from "react";

import { useProjectData } from "./useProjectData";
import { apiJson } from "../services/apiClient";
import { computeWizardProgress, onWizardProgressInvalidated, type WizardProgress } from "../services/wizard";
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
  const [, setVersion] = useState(0);

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
  const { data, loading, refresh } = wizardQuery;

  const refreshDebounceRef = useRef<number | null>(null);
  const loadingRef = useRef(false);

  useEffect(() => {
    loadingRef.current = loading;
  }, [loading]);

  const bumpLocal = useCallback(() => {
    setVersion((v) => v + 1);
  }, []);

  useEffect(() => {
    if (!projectId) return;
    const off = onWizardProgressInvalidated((detail) => {
      if (detail.projectId !== projectId) return;
      bumpLocal();
      if (!detail.refresh) return;
      if (refreshDebounceRef.current !== null) {
        window.clearTimeout(refreshDebounceRef.current);
      }
      refreshDebounceRef.current = window.setTimeout(() => {
        refreshDebounceRef.current = null;
        if (loadingRef.current) return;
        void refresh();
      }, 80);
    });
    return () => {
      off();
      if (refreshDebounceRef.current !== null) {
        window.clearTimeout(refreshDebounceRef.current);
        refreshDebounceRef.current = null;
      }
    };
  }, [bumpLocal, projectId, refresh]);

  const project = data?.project ?? null;
  const selectedProfileId = project?.llm_profile_id ?? null;
  const profiles = data?.profiles ?? [];
  const llmProfile = selectedProfileId ? (profiles.find((p) => p.id === selectedProfileId) ?? null) : null;
  const progress = computeWizardProgress({
    project,
    settings: data?.settings ?? null,
    characters: data?.characters ?? EMPTY_CHARACTERS,
    outline: data?.outline ?? null,
    chapters: data?.chapters ?? EMPTY_CHAPTERS,
    llmPreset: data?.llmPreset ?? null,
    llmProfile,
  });

  return {
    loading,
    progress,
    refresh,
    bumpLocal,
  };
}
