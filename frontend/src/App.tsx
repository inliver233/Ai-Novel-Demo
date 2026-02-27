import { Suspense, lazy } from "react";
import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";

import { AuthGuard } from "./components/layout/AuthGuard";
import { ProjectProviderGuard } from "./components/layout/ProjectProviderGuard";
import { AppShell } from "./components/layout/AppShell";
import { ConfirmProvider } from "./components/ui/ConfirmProvider";
import { ToastProvider } from "./components/ui/ToastProvider";
import { AuthProvider } from "./contexts/AuthContext";
import { ProjectsProvider } from "./contexts/ProjectsContext";

const LoginPage = lazy(async () => {
  const mod = await import("./pages/LoginPage");
  return { default: mod.LoginPage };
});

const RegisterPage = lazy(async () => {
  const mod = await import("./pages/RegisterPage");
  return { default: mod.RegisterPage };
});

const DashboardPage = lazy(async () => {
  const mod = await import("./pages/DashboardPage");
  return { default: mod.DashboardPage };
});

const AdminUsersPage = lazy(async () => {
  const mod = await import("./pages/AdminUsersPage");
  return { default: mod.AdminUsersPage };
});

const ProjectWizardPage = lazy(async () => {
  const mod = await import("./pages/ProjectWizardPage");
  return { default: mod.ProjectWizardPage };
});

const SettingsPage = lazy(async () => {
  const mod = await import("./pages/SettingsPage");
  return { default: mod.SettingsPage };
});

const CharactersPage = lazy(async () => {
  const mod = await import("./pages/CharactersPage");
  return { default: mod.CharactersPage };
});

const OutlinePage = lazy(async () => {
  const mod = await import("./pages/OutlinePage");
  return { default: mod.OutlinePage };
});

const WritingPage = lazy(async () => {
  const mod = await import("./pages/WritingPage");
  return { default: mod.WritingPage };
});

const TaskCenterPage = lazy(async () => {
  const mod = await import("./pages/TaskCenterPage");
  return { default: mod.TaskCenterPage };
});

const StructuredMemoryPage = lazy(async () => {
  const mod = await import("./pages/StructuredMemoryPage");
  return { default: mod.StructuredMemoryPage };
});

const NumericTablesPage = lazy(async () => {
  const mod = await import("./pages/NumericTablesPage");
  return { default: mod.NumericTablesPage };
});

const ForeshadowsPage = lazy(async () => {
  const mod = await import("./pages/ForeshadowsPage");
  return { default: mod.ForeshadowsPage };
});

const ChapterAnalysisPage = lazy(async () => {
  const mod = await import("./pages/ChapterAnalysisPage");
  return { default: mod.ChapterAnalysisPage };
});

const PreviewPage = lazy(async () => {
  const mod = await import("./pages/PreviewPage");
  return { default: mod.PreviewPage };
});

const ChapterReaderPage = lazy(async () => {
  const mod = await import("./pages/ChapterReaderPage");
  return { default: mod.ChapterReaderPage };
});

const PromptsPage = lazy(async () => {
  const mod = await import("./pages/PromptsPage");
  return { default: mod.PromptsPage };
});

const PromptStudioPage = lazy(async () => {
  const mod = await import("./pages/PromptStudioPage");
  return { default: mod.PromptStudioPage };
});

const PromptTemplatesPage = lazy(async () => {
  const mod = await import("./pages/PromptTemplatesPage");
  return { default: mod.PromptTemplatesPage };
});

const ExportPage = lazy(async () => {
  const mod = await import("./pages/ExportPage");
  return { default: mod.ExportPage };
});

const WorldBookPage = lazy(async () => {
  const mod = await import("./pages/WorldBookPage");
  return { default: mod.WorldBookPage };
});

const GraphPage = lazy(async () => {
  const mod = await import("./pages/GraphPage");
  return { default: mod.GraphPage };
});

const FractalPage = lazy(async () => {
  const mod = await import("./pages/FractalPage");
  return { default: mod.FractalPage };
});

const StylesPage = lazy(async () => {
  const mod = await import("./pages/StylesPage");
  return { default: mod.StylesPage };
});

const RagPage = lazy(async () => {
  const mod = await import("./pages/RagPage");
  return { default: mod.RagPage };
});

const ImportPage = lazy(async () => {
  const mod = await import("./pages/ImportPage");
  return { default: mod.ImportPage };
});

const SearchPage = lazy(async () => {
  const mod = await import("./pages/SearchPage");
  return { default: mod.SearchPage };
});

const NotFoundPage = lazy(async () => {
  const mod = await import("./pages/NotFoundPage");
  return { default: mod.NotFoundPage };
});

const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/register",
    element: <RegisterPage />,
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
                path: "numeric-tables",
                element: <NumericTablesPage />,
              },
              {
                path: "foreshadows",
                element: <ForeshadowsPage />,
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
                path: "reader",
                element: <ChapterReaderPage />,
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
                path: "prompt-templates",
                element: <PromptTemplatesPage />,
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
                path: "fractal",
                element: <FractalPage />,
              },
              {
                path: "styles",
                element: <StylesPage />,
              },
              {
                path: "rag",
                element: <RagPage />,
              },
              {
                path: "import",
                element: <ImportPage />,
              },
              {
                path: "glossary",
                element: <Navigate to="../search" replace />,
              },
              {
                path: "search",
                element: <SearchPage />,
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
          <Suspense fallback={<div className="p-4 text-sm text-subtext">加载中…</div>}>
            <RouterProvider router={router} />
          </Suspense>
        </AuthProvider>
      </ConfirmProvider>
    </ToastProvider>
  );
}
