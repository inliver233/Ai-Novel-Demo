import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";

import { ProjectProviderGuard } from "./components/layout/ProjectProviderGuard";
import { AppShell } from "./components/layout/AppShell";
import { ConfirmProvider } from "./components/ui/ConfirmProvider";
import { ToastProvider } from "./components/ui/ToastProvider";
import { ProjectsProvider } from "./contexts/ProjectsContext";
import { CharactersPage } from "./pages/CharactersPage";
import { DashboardPage } from "./pages/DashboardPage";
import { ExportPage } from "./pages/ExportPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OutlinePage } from "./pages/OutlinePage";
import { PreviewPage } from "./pages/PreviewPage";
import { ProjectWizardPage } from "./pages/ProjectWizardPage";
import { PromptsPage } from "./pages/PromptsPage";
import { PromptStudioPage } from "./pages/PromptStudioPage";
import { SettingsPage } from "./pages/SettingsPage";
import { WritingPage } from "./pages/WritingPage";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      {
        path: "projects/:projectId",
        element: <ProjectProviderGuard />,
        children: [
          { index: true, element: <Navigate to="writing" replace /> },
          { path: "wizard", element: <ProjectWizardPage /> },
          { path: "settings", element: <SettingsPage /> },
          { path: "characters", element: <CharactersPage /> },
          { path: "outline", element: <OutlinePage /> },
          { path: "writing", element: <WritingPage /> },
          { path: "preview", element: <PreviewPage /> },
          { path: "prompts", element: <PromptsPage /> },
          { path: "prompt-studio", element: <PromptStudioPage /> },
          { path: "export", element: <ExportPage /> },
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
