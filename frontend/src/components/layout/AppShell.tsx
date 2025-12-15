import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import {
  BookOpenText,
  FileDown,
  LayoutDashboard,
  ListChecks,
  PanelLeftClose,
  PanelLeftOpen,
  PenLine,
  Settings,
  Sparkles,
  Users,
} from "lucide-react";
import { useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useParams } from "react-router-dom";

import { ProjectSwitcher } from "../atelier/ProjectSwitcher";
import { ThemeToggle } from "../atelier/ThemeToggle";
import { getCurrentUserId } from "../../services/currentUser";
import { sidebarCollapsedStorageKey } from "../../services/uiState";

const ROUTE_TITLES: Array<[suffix: string, title: string]> = [
  ["/settings", "设定"],
  ["/characters", "角色卡"],
  ["/outline", "大纲"],
  ["/wizard", "开工向导"],
  ["/writing", "写作"],
  ["/prompts", "Prompt & 模型"],
  ["/export", "导出"],
];

function resolveTitle(pathname: string): string {
  if (pathname === "/") return "Dashboard";
  const match = ROUTE_TITLES.find(([suffix]) => pathname.endsWith(suffix));
  return match?.[1] ?? "ainovel Atelier";
}

function useSidebarCollapsed(): [boolean, (v: boolean) => void] {
  const storageKey = sidebarCollapsedStorageKey(getCurrentUserId());
  const [collapsed, setCollapsed] = useState<boolean>(() => localStorage.getItem(storageKey) === "1");
  return [
    collapsed,
    (v) => {
      setCollapsed(v);
      localStorage.setItem(storageKey, v ? "1" : "0");
    },
  ];
}

function SidebarLink(props: { to: string; icon: React.ReactNode; label: string; collapsed: boolean }) {
  return (
    <NavLink
      className={({ isActive }) =>
        clsx(
          "flex w-full items-center rounded-atelier py-2 text-sm no-underline hover:no-underline",
          props.collapsed ? "justify-center px-0" : "justify-start gap-3 px-3",
          isActive ? "bg-canvas text-ink" : "text-subtext hover:bg-canvas hover:text-ink",
        )
      }
      to={props.to}
      aria-label={props.label}
      title={props.collapsed ? props.label : undefined}
    >
      <span className="shrink-0">{props.icon}</span>
      {props.collapsed ? null : <span className="min-w-0 truncate">{props.label}</span>}
    </NavLink>
  );
}

export function AppShell() {
  const [collapsed, setCollapsed] = useSidebarCollapsed();
  const { projectId } = useParams();
  const location = useLocation();

  const title = useMemo(() => resolveTitle(location.pathname), [location.pathname]);

  const CollapseIcon = collapsed ? PanelLeftOpen : PanelLeftClose;
  const collapseLabel = collapsed ? "展开侧边栏" : "收起侧边栏";

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <div className="flex">
        <aside
          className={clsx(
            "min-h-screen shrink-0 overflow-x-hidden border-r border-border bg-surface transition-[width] duration-300 ease-out",
            collapsed ? "w-14 p-2" : "w-[260px] p-4",
          )}
        >
          <div className={clsx("flex gap-2", collapsed ? "flex-col items-center" : "items-center justify-between")}>
            {collapsed ? null : <div className="font-content text-lg">ainovel Atelier</div>}
            <div className={clsx("flex gap-2", collapsed ? "flex-col items-center" : "items-center")}>
              <ThemeToggle />
              <button
                className="rounded-atelier border border-border bg-surface px-2 py-2 text-ink hover:bg-canvas"
                onClick={() => setCollapsed(!collapsed)}
                aria-label={collapseLabel}
                title={collapseLabel}
                type="button"
              >
                <CollapseIcon size={18} />
              </button>
            </div>
          </div>

          <div className={clsx("mt-4", collapsed && "hidden")}>
            <ProjectSwitcher />
          </div>

          <nav className="mt-4 flex flex-col gap-1">
            <SidebarLink collapsed={collapsed} icon={<LayoutDashboard size={18} />} label="Dashboard" to="/" />
            <div className="my-2 h-px bg-border" />
            {projectId ? (
              <>
                <SidebarLink
                  collapsed={collapsed}
                  icon={<ListChecks size={18} />}
                  label="向导"
                  to={`/projects/${projectId}/wizard`}
                />
                <SidebarLink
                  collapsed={collapsed}
                  icon={<Settings size={18} />}
                  label="设定"
                  to={`/projects/${projectId}/settings`}
                />
                <SidebarLink
                  collapsed={collapsed}
                  icon={<Users size={18} />}
                  label="角色卡"
                  to={`/projects/${projectId}/characters`}
                />
                <SidebarLink
                  collapsed={collapsed}
                  icon={<BookOpenText size={18} />}
                  label="大纲"
                  to={`/projects/${projectId}/outline`}
                />
                <SidebarLink
                  collapsed={collapsed}
                  icon={<PenLine size={18} />}
                  label="写作"
                  to={`/projects/${projectId}/writing`}
                />
                <SidebarLink
                  collapsed={collapsed}
                  icon={<Sparkles size={18} />}
                  label="Prompt & 模型"
                  to={`/projects/${projectId}/prompts`}
                />
                <SidebarLink
                  collapsed={collapsed}
                  icon={<FileDown size={18} />}
                  label="导出"
                  to={`/projects/${projectId}/export`}
                />
              </>
            ) : (
              <div className={clsx("rounded-atelier border border-border bg-canvas p-3 text-xs text-subtext", collapsed && "hidden")}>
                请选择一个项目以进入编辑页。
              </div>
            )}
          </nav>
        </aside>

        <main className="flex-1">
          <header className="border-b border-border bg-canvas">
            <div className="mx-auto max-w-4xl px-8 py-6">
              <h1 className="font-content text-3xl">{title}</h1>
            </div>
          </header>
          <div className="mx-auto max-w-4xl px-8 py-8">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={location.pathname}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                transition={{ duration: 0.4, ease: "easeOut" }}
              >
                <Outlet />
              </motion.div>
            </AnimatePresence>
          </div>
        </main>
      </div>
    </div>
  );
}
