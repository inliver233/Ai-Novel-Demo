import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";

import { ProjectProviderGuard } from "./components/layout/ProjectProviderGuard";
import { AppShell } from "./components/layout/AppShell";
import { ConfirmProvider } from "./components/ui/ConfirmProvider";
import { ToastProvider } from "./components/ui/ToastProvider";
import { ProjectsProvider } from "./contexts/ProjectsContext";
import { DashboardPage } from "./pages/DashboardPage";
import { ProjectWizardPage } from "./pages/ProjectWizardPage";
import { SettingsPage } from "./pages/SettingsPage";
import { CharactersPage } from "./pages/CharactersPage";
import { OutlinePage } from "./pages/OutlinePage";
import { WritingPage } from "./pages/WritingPage";
import { ChapterAnalysisPage } from "./pages/ChapterAnalysisPage";
import { PreviewPage } from "./pages/PreviewPage";
import { PromptsPage } from "./pages/PromptsPage";
import { PromptStudioPage } from "./pages/PromptStudioPage";
import { ExportPage } from "./pages/ExportPage";
import { WorldBookPage } from "./pages/WorldBookPage";
import { NotFoundPage } from "./pages/NotFoundPage";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      {
        index: true,
        element: <DashboardPage />,
      },
      {
        path: "projects/:projectId",
        element: <ProjectProviderGuard />,
        children: [
          { index: true, element: <Navigate to="writing" replace /> },
          {
            path: "wizard",
            element: <ProjectWizardPage />,
          },
          {
            path: "settings",
            element: <SettingsPage />,
          },
          {
            path: "characters",
            element: <CharactersPage />,
          },
          {
            path: "outline",
            element: <OutlinePage />,
          },
          {
            path: "writing",
            element: <WritingPage />,
          },
          {
            path: "chapter-analysis",
            element: <ChapterAnalysisPage />,
          },
          {
            path: "preview",
            element: <PreviewPage />,
          },
          {
            path: "prompts",
            element: <PromptsPage />,
          },
          {
            path: "prompt-studio",
            element: <PromptStudioPage />,
          },
          {
            path: "export",
            element: <ExportPage />,
          },
          {
            path: "worldbook",
            element: <WorldBookPage />,
          },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);

export default function App() {
  return (
    <ToastProvider>
      <ConfirmProvider>
        <ProjectsProvider>
          <RouterProvider router={router} />
        </ProjectsProvider>
      </ConfirmProvider>
    </ToastProvider>
  );
}
