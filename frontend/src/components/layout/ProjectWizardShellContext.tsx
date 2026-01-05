import { createContext, useContext, useLayoutEffect } from "react";
import type { Dispatch, SetStateAction } from "react";

import type { WizardProgress, WizardStepKey } from "../../services/wizard";
import type { WizardPrimaryAction } from "../atelier/WizardNextBar";

export type WizardBarConfig = {
  currentStep: WizardStepKey;
  dirty?: boolean;
  saving?: boolean;
  onSave?: () => Promise<boolean>;
  primaryAction?: WizardPrimaryAction;
};

export type ProjectWizardShellContextValue = {
  loading: boolean;
  progress: WizardProgress;
  refreshWizard: () => Promise<void>;
  bumpWizardLocal: () => void;
  setBarConfig: Dispatch<SetStateAction<WizardBarConfig | null>>;
};

export const ProjectWizardShellContext = createContext<ProjectWizardShellContextValue | null>(null);

function isSamePrimaryAction(a: WizardPrimaryAction | undefined, b: WizardPrimaryAction | undefined): boolean {
  if (!a && !b) return true;
  if (!a || !b) return false;
  return a.label === b.label && Boolean(a.disabled) === Boolean(b.disabled) && a.onClick === b.onClick;
}

function isSameWizardBarConfig(a: WizardBarConfig | null, b: WizardBarConfig): boolean {
  if (!a) return false;
  return (
    a.currentStep === b.currentStep &&
    Boolean(a.dirty) === Boolean(b.dirty) &&
    Boolean(a.saving) === Boolean(b.saving) &&
    a.onSave === b.onSave &&
    isSamePrimaryAction(a.primaryAction, b.primaryAction)
  );
}

export function useProjectWizardShell(): ProjectWizardShellContextValue {
  const ctx = useContext(ProjectWizardShellContext);
  if (!ctx) throw new Error("useProjectWizardShell must be used within ProjectWizardShell");
  return ctx;
}

export function useWizardBar(config: WizardBarConfig) {
  const { setBarConfig } = useProjectWizardShell();
  useLayoutEffect(() => {
    setBarConfig((prev) => (isSameWizardBarConfig(prev, config) ? prev : config));
  }, [config, setBarConfig]);
}
