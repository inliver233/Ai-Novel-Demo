import { Suspense } from "react";
import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";

import { ProjectProviderGuard } from "./components/layout/ProjectProviderGuard";
import { AppShell } from "./components/layout/AppShell";
import { ConfirmProvider } from "./components/ui/ConfirmProvider";
import { ToastProvider } from "./components/ui/ToastProvider";
import { ProjectsProvider } from "./contexts/ProjectsContext";
import { UI_COPY } from "./lib/uiCopy";
import { NotFoundPage } from "./pages/NotFoundPage";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      {
        index: true,
        lazy: async () => {
          const mod = await import("./pages/DashboardPage");
          return { Component: mod.DashboardPage };
        },
      },
      {
        path: "projects/:projectId",
        element: <ProjectProviderGuard />,
        children: [
          { index: true, element: <Navigate to="writing" replace /> },
          {
            path: "wizard",
            lazy: async () => {
              const mod = await import("./pages/ProjectWizardPage");
              return { Component: mod.ProjectWizardPage };
            },
          },
          {
            path: "settings",
            lazy: async () => {
              const mod = await import("./pages/SettingsPage");
              return { Component: mod.SettingsPage };
            },
          },
          {
            path: "characters",
            lazy: async () => {
              const mod = await import("./pages/CharactersPage");
              return { Component: mod.CharactersPage };
            },
          },
          {
            path: "outline",
            lazy: async () => {
              const mod = await import("./pages/OutlinePage");
              return { Component: mod.OutlinePage };
            },
          },
          {
            path: "writing",
            lazy: async () => {
              const mod = await import("./pages/WritingPage");
              return { Component: mod.WritingPage };
            },
          },
          {
            path: "preview",
            lazy: async () => {
              const mod = await import("./pages/PreviewPage");
              return { Component: mod.PreviewPage };
            },
          },
          {
            path: "prompts",
            lazy: async () => {
              const mod = await import("./pages/PromptsPage");
              return { Component: mod.PromptsPage };
            },
          },
          {
            path: "prompt-studio",
            lazy: async () => {
              const mod = await import("./pages/PromptStudioPage");
              return { Component: mod.PromptStudioPage };
            },
          },
          {
            path: "export",
            lazy: async () => {
              const mod = await import("./pages/ExportPage");
              return { Component: mod.ExportPage };
            },
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
          <Suspense fallback={<div className="p-6 text-subtext">{UI_COPY.common.loading}</div>}>
            <RouterProvider router={router} />
          </Suspense>
        </ProjectsProvider>
      </ConfirmProvider>
    </ToastProvider>
  );
}
