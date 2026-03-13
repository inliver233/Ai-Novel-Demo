import { WizardNextBar } from "../components/atelier/WizardNextBar";
import { ToolContent } from "../components/layout/AppShell";
import { UnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";

import {
  WritingChapterListDrawer,
  WritingPageOverlays,
  WritingStreamFloatingCard,
  WritingWorkspace,
} from "./writing/WritingPageSections";
import { WRITING_PAGE_COPY } from "./writing/writingPageCopy";
import { useWritingPageState } from "./writing/useWritingPageState";

export function WritingPage() {
  const state = useWritingPageState();

  if (state.loading) {
    return <ToolContent className="text-subtext">{WRITING_PAGE_COPY.loading}</ToolContent>;
  }

  return (
    <ToolContent className="grid gap-4 pb-24">
      {state.showUnsavedGuard ? <UnsavedChangesGuard when={state.dirty} /> : null}
      <WritingWorkspace {...state.workspaceProps} />
      <WritingChapterListDrawer {...state.chapterListDrawerProps} />
      <WritingPageOverlays {...state.overlaysProps} />
      <WritingStreamFloatingCard {...state.streamFloatingProps} />
      <WizardNextBar {...state.wizardBarProps} />
    </ToolContent>
  );
}
