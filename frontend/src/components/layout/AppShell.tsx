import clsx from "clsx";
import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from "framer-motion";
import {
  Bot,
  Book,
  BookOpen,
  BookOpenText,
  FileDown,
  LayoutDashboard,
  ListChecks,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  PenLine,
  Share2,
  Settings,
  Sparkles,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { NavLink, useLocation, useNavigate, useOutlet, useParams } from "react-router-dom";

import { ProjectSwitcher } from "../atelier/ProjectSwitcher";
import { ThemeToggle } from "../atelier/ThemeToggle";
import { useAuth } from "../../contexts/auth";
import { UI_COPY } from "../../lib/uiCopy";
import { transition } from "../../lib/motion";
import { getCurrentUserId } from "../../services/currentUser";
import { sidebarCollapsedStorageKey } from "../../services/uiState";

const ROUTE_TITLES: Array<[suffix: string, title: string]> = [
  ["/settings", "设定"],
  ["/characters", "角色卡"],
  ["/outline", "大纲"],
  ["/wizard", "开工向导"],
  ["/writing", "写作"],
  ["/graph", "图谱"],
  ["/styles", "风格"],
  ["/chapter-analysis", "标注回溯"],
  ["/worldbook", "世界书"],
  ["/prompts", "模型配置"],
  ["/prompt-studio", "Prompt Studio"],
  ["/preview", "预览"],
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

function SidebarLink(props: {
  to: string;
  icon: React.ReactNode;
  label: string;
  collapsed: boolean;
  onClick?: () => void;
}) {
  return (
    <NavLink
      className={({ isActive }) =>
        clsx(
          "ui-focus-ring ui-transition-fast group relative flex w-full items-center overflow-hidden rounded-atelier py-2 text-sm no-underline hover:no-underline motion-safe:active:scale-[0.99]",
          props.collapsed ? "justify-center px-0" : "justify-start gap-3 px-3",
          isActive ? "text-ink" : "text-subtext hover:bg-canvas hover:text-ink",
        )
      }
      to={props.to}
      aria-label={props.label}
      title={props.collapsed ? props.label : undefined}
      onClick={props.onClick}
    >
      {({ isActive }) => (
        <>
          {isActive ? (
            <motion.span
              layoutId="atelier-sidebar-active"
              className="absolute inset-0 rounded-atelier bg-canvas"
              transition={transition.fast}
            />
          ) : null}
          <span className="relative z-10 shrink-0">{props.icon}</span>
          {props.collapsed ? null : <span className="relative z-10 min-w-0 truncate">{props.label}</span>}
        </>
      )}
    </NavLink>
  );
}

function PersistentOutlet(props: { activeKey: string }) {
  const outlet = useOutlet();
  const [cache, setCache] = useState<Map<string, React.ReactNode>>(() => new Map([[props.activeKey, outlet]]));

  const cacheWithActive = useMemo(() => {
    if (cache.has(props.activeKey)) return cache;
    const next = new Map(cache);
    next.set(props.activeKey, outlet);
    return next;
  }, [cache, outlet, props.activeKey]);

  useEffect(() => {
    if (cacheWithActive === cache) return;
    const id = window.setTimeout(() => setCache(cacheWithActive), 0);
    return () => window.clearTimeout(id);
  }, [cache, cacheWithActive]);

  return (
    <>
      {Array.from(cacheWithActive.entries()).map(([key, element]) => (
        <div key={key} style={{ display: key === props.activeKey ? "block" : "none" }}>
          {element}
        </div>
      ))}
    </>
  );
}

export function AppShell() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useSidebarCollapsed();
  const [mobileNavOpenForPath, setMobileNavOpenForPath] = useState<string | null>(null);
  const { projectId } = useParams();
  const location = useLocation();
  const reduceMotion = useReducedMotion();

  const title = useMemo(() => resolveTitle(location.pathname), [location.pathname]);
  const sessionExpireAtText = auth.session?.expireAt ? new Date(auth.session.expireAt * 1000).toLocaleString() : null;
  const mobileNavOpen = mobileNavOpenForPath === location.pathname;

  const CollapseIcon = collapsed ? PanelLeftOpen : PanelLeftClose;
  const collapseLabel = collapsed ? "展开侧边栏" : "收起侧边栏";

  const openMobileNav = () => setMobileNavOpenForPath(location.pathname);
  const closeMobileNav = () => setMobileNavOpenForPath(null);

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <div className="flex">
        <AnimatePresence>
          {mobileNavOpen ? (
            <motion.div
              className="fixed inset-0 z-50 flex bg-black/30 lg:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={reduceMotion ? { duration: 0.01 } : transition.base}
              onClick={(e) => {
                if (e.target === e.currentTarget) closeMobileNav();
              }}
              role="dialog"
              aria-modal="true"
              aria-label="导航菜单"
            >
              <motion.aside
                className="h-full w-[280px] shrink-0 overflow-x-hidden border-r border-border bg-surface p-4 shadow-sm"
                initial={{ x: -12, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                exit={{ x: -12, opacity: 0 }}
                transition={reduceMotion ? { duration: 0.01 } : transition.base}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="font-content text-lg">ainovel Atelier</div>
                  <button
                    className="btn btn-secondary btn-icon"
                    onClick={closeMobileNav}
                    aria-label="关闭导航"
                    title="关闭导航"
                    type="button"
                  >
                    <PanelLeftClose size={18} />
                  </button>
                </div>

                <div className="mt-4">
                  <ProjectSwitcher />
                </div>

                <LayoutGroup id="atelier-sidebar-mobile">
                  <nav className="mt-4 flex flex-col gap-1">
                    <SidebarLink
                      collapsed={false}
                      icon={<LayoutDashboard size={18} />}
                      label="Dashboard"
                      to="/"
                      onClick={closeMobileNav}
                    />
                    <div className="my-2 h-px bg-border" />
                    {projectId ? (
                      <>
                        <SidebarLink
                          collapsed={false}
                          icon={<ListChecks size={18} />}
                          label="向导"
                          to={`/projects/${projectId}/wizard`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<Settings size={18} />}
                          label="设定"
                          to={`/projects/${projectId}/settings`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<Book size={18} />}
                          label="世界书"
                          to={`/projects/${projectId}/worldbook`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<Users size={18} />}
                          label="角色卡"
                          to={`/projects/${projectId}/characters`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<BookOpenText size={18} />}
                          label="大纲"
                          to={`/projects/${projectId}/outline`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<PenLine size={18} />}
                          label="写作"
                          to={`/projects/${projectId}/writing`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<Share2 size={18} />}
                          label="图谱"
                          to={`/projects/${projectId}/graph`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<Bot size={18} />}
                          label="模型配置"
                          to={`/projects/${projectId}/prompts`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<Palette size={18} />}
                          label="风格"
                          to={`/projects/${projectId}/styles`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<Sparkles size={18} />}
                          label="Prompt Studio"
                          to={`/projects/${projectId}/prompt-studio`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<BookOpen size={18} />}
                          label="预览"
                          to={`/projects/${projectId}/preview`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<FileDown size={18} />}
                          label="导出"
                          to={`/projects/${projectId}/export`}
                          onClick={closeMobileNav}
                        />
                      </>
                    ) : (
                      <div className="rounded-atelier border border-border bg-canvas p-3 text-xs text-subtext">
                        请选择一个项目以进入编辑页。
                      </div>
                    )}
                  </nav>
                </LayoutGroup>
              </motion.aside>
            </motion.div>
          ) : null}
        </AnimatePresence>

        <aside
          className={clsx(
            "hidden min-h-screen shrink-0 overflow-x-hidden border-r border-border bg-surface motion-safe:transition-[width] motion-safe:duration-atelier motion-safe:ease-atelier lg:block",
            collapsed ? "w-14 p-2" : "w-[260px] p-4",
          )}
        >
          <div className={clsx("flex gap-2", collapsed ? "flex-col items-center" : "items-center justify-between")}>
            {collapsed ? null : <div className="font-content text-lg">ainovel Atelier</div>}
            <div className={clsx("flex gap-2", collapsed ? "flex-col items-center" : "items-center")}>
              <ThemeToggle />
              <button
                className="btn btn-secondary btn-icon"
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

          <LayoutGroup id="atelier-sidebar-desktop">
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
                    icon={<Book size={18} />}
                    label="世界书"
                    to={`/projects/${projectId}/worldbook`}
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
                    icon={<Share2 size={18} />}
                    label="图谱"
                    to={`/projects/${projectId}/graph`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<Bot size={18} />}
                    label="模型配置"
                    to={`/projects/${projectId}/prompts`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<Palette size={18} />}
                    label="风格"
                    to={`/projects/${projectId}/styles`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<Sparkles size={18} />}
                    label="Prompt Studio"
                    to={`/projects/${projectId}/prompt-studio`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<BookOpen size={18} />}
                    label="预览"
                    to={`/projects/${projectId}/preview`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<FileDown size={18} />}
                    label="导出"
                    to={`/projects/${projectId}/export`}
                  />
                </>
              ) : (
                <div
                  className={clsx(
                    "rounded-atelier border border-border bg-canvas p-3 text-xs text-subtext",
                    collapsed && "hidden",
                  )}
                >
                  请选择一个项目以进入编辑页。
                </div>
              )}
            </nav>
          </LayoutGroup>
        </aside>

        <main className="flex-1">
          <header className="border-b border-border bg-canvas">
            <div className="mx-auto max-w-screen-xl px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
              <div className="flex items-center justify-between gap-4">
                <div className="flex min-w-0 items-center gap-3">
                  <button
                    className="btn btn-secondary btn-icon lg:hidden"
                    onClick={openMobileNav}
                    aria-label="打开导航"
                    title="打开导航"
                    type="button"
                  >
                    <PanelLeftOpen size={18} />
                  </button>
                  <h1 className="min-w-0 truncate font-content text-2xl sm:text-3xl">{title}</h1>
                </div>
                <div className="flex items-center gap-2">
                  <div className="hidden text-right text-xs text-subtext sm:block">
                    <div className="truncate">
                      {auth.status === "authenticated"
                        ? `${auth.user?.displayName ?? auth.user?.id ?? "user"} (${auth.user?.id ?? "unknown"})`
                        : UI_COPY.auth.devFallbackTag}
                    </div>
                    {auth.status === "authenticated" && sessionExpireAtText ? (
                      <div className="truncate">
                        {UI_COPY.auth.sessionExpireAtPrefix}
                        {sessionExpireAtText}
                      </div>
                    ) : null}
                  </div>

                  {auth.status === "authenticated" ? (
                    <button
                      className="btn btn-secondary"
                      onClick={async () => {
                        await auth.logout();
                        navigate("/login", { replace: true });
                      }}
                      type="button"
                    >
                      {UI_COPY.auth.logout}
                    </button>
                  ) : (
                    <NavLink className="btn btn-secondary" to="/login">
                      {UI_COPY.auth.login}
                    </NavLink>
                  )}

                  <div className="lg:hidden">
                    <ThemeToggle />
                  </div>
                </div>
              </div>
            </div>
          </header>
          <div className="mx-auto max-w-screen-xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
            <PersistentOutlet activeKey={location.pathname} />
          </div>
        </main>
      </div>
    </div>
  );
}
