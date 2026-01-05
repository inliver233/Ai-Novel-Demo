import { useMemo, useState } from "react";
import { useLocation } from "react-router-dom";

import { useWizardProgress } from "../../hooks/useWizardProgress";
import { WizardNextBar } from "../atelier/WizardNextBar";
import {
  ProjectWizardShellContext,
  type ProjectWizardShellContextValue,
  type WizardBarConfig,
} from "./ProjectWizardShellContext";

export function ProjectWizardShell(props: { projectId: string; children: React.ReactNode }) {
  const { projectId, children } = props;
  const location = useLocation();
  const wizard = useWizardProgress(projectId);
  const [barConfig, setBarConfig] = useState<WizardBarConfig | null>(null);

  const ctxValue = useMemo<ProjectWizardShellContextValue>(
    () => ({
      loading: wizard.loading,
      progress: wizard.progress,
      refreshWizard: wizard.refresh,
      bumpWizardLocal: wizard.bumpLocal,
      setBarConfig,
    }),
    [wizard.bumpLocal, wizard.loading, wizard.progress, wizard.refresh],
  );

  const hideBar = location.pathname.endsWith("/wizard") || location.pathname.endsWith("/prompt-studio");
  const showBar = Boolean(barConfig && !hideBar);

  return (
    <ProjectWizardShellContext.Provider value={ctxValue}>
      {children}
      {showBar ? (
        <WizardNextBar
          projectId={projectId}
          currentStep={barConfig!.currentStep}
          progress={wizard.progress}
          loading={wizard.loading}
          dirty={barConfig!.dirty}
          saving={barConfig!.saving}
          onSave={barConfig!.onSave}
          primaryAction={barConfig!.primaryAction}
        />
      ) : null}
    </ProjectWizardShellContext.Provider>
  );
}
