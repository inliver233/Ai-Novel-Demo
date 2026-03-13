import { WizardNextBar } from "../components/atelier/WizardNextBar";
import { UnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";

import {
  OutlineActionsBar,
  OutlineEditorSection,
  OutlineGenerationModal,
  OutlineGuideSection,
  OutlineHeaderSection,
  OutlineTitleModal,
} from "./outline/OutlinePageSections";
import { OUTLINE_COPY } from "./outline/outlineCopy";
import { useOutlinePageState } from "./outline/useOutlinePageState";

export function OutlinePage() {
  const state = useOutlinePageState();

  if (state.loading) return <div className="text-subtext">{OUTLINE_COPY.loading}</div>;

  return (
    <div className="grid gap-4 pb-[calc(6rem+env(safe-area-inset-bottom))]">
      {state.showUnsavedGuard ? <UnsavedChangesGuard when={state.dirty} /> : null}
      <OutlineHeaderSection {...state.headerProps} />
      <OutlineActionsBar {...state.actionsBarProps} />
      <OutlineGuideSection />
      <OutlineEditorSection {...state.editorProps} />
      <OutlineTitleModal {...state.titleModalProps} />
      <OutlineGenerationModal {...state.generationModalProps} />
      <WizardNextBar {...state.wizardBarProps} />
    </div>
  );
}
