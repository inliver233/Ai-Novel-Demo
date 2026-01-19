import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";

import { AuthGuard } from "./components/layout/AuthGuard";
import { ProjectProviderGuard } from "./components/layout/ProjectProviderGuard";
import { AppShell } from "./components/layout/AppShell";
import { ConfirmProvider } from "./components/ui/ConfirmProvider";
import { ToastProvider } from "./components/ui/ToastProvider";
import { AuthProvider } from "./contexts/AuthContext";
import { ProjectsProvider } from "./contexts/ProjectsContext";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { ProjectWizardPage } from "./pages/ProjectWizardPage";
import { SettingsPage } from "./pages/SettingsPage";
import { CharactersPage } from "./pages/CharactersPage";
import { OutlinePage } from "./pages/OutlinePage";
import { WritingPage } from "./pages/WritingPage";
import { TaskCenterPage } from "./pages/TaskCenterPage";
import { StructuredMemoryPage } from "./pages/StructuredMemoryPage";
import { ChapterAnalysisPage } from "./pages/ChapterAnalysisPage";
import { PreviewPage } from "./pages/PreviewPage";
import { PromptsPage } from "./pages/PromptsPage";
import { PromptStudioPage } from "./pages/PromptStudioPage";
import { ExportPage } from "./pages/ExportPage";
import { GraphPage } from "./pages/GraphPage";
import { StylesPage } from "./pages/StylesPage";
import { WorldBookPage } from "./pages/WorldBookPage";
import { RagPage } from "./pages/RagPage";
import { AdminUsersPage } from "./pages/AdminUsersPage";
import { NotFoundPage } from "./pages/NotFoundPage";

const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    element: <AuthGuard />,
    children: [
      {
        path: "/",
        element: (
          <ProjectsProvider>
            <AppShell />
          </ProjectsProvider>
        ),
        children: [
          {
            index: true,
            element: <DashboardPage />,
          },
          {
            path: "admin/users",
            element: <AdminUsersPage />,
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
                path: "tasks",
                element: <TaskCenterPage />,
              },
              {
                path: "structured-memory",
                element: <StructuredMemoryPage />,
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
              {
                path: "graph",
                element: <GraphPage />,
              },
              {
                path: "styles",
                element: <StylesPage />,
              },
              {
                path: "rag",
                element: <RagPage />,
              },
            ],
          },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
]);

export default function App() {
  return (
    <ToastProvider>
      <ConfirmProvider>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </ConfirmProvider>
    </ToastProvider>
  );
}
