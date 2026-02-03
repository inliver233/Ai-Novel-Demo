import clsx from "clsx";
import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from "framer-motion";
import {
  Bot,
  BookOpen,
  BookOpenText,
  BookText,
  CircleHelp,
  Database,
  FileDown,
  Globe,
  LayoutDashboard,
  ListTodo,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  PenLine,
  Share2,
  Settings,
  Snowflake,
  Sparkles,
  TableOfContents,
  Table2,
  UserCog,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate, useOutlet, useParams } from "react-router-dom";

import { ProjectSwitcher } from "../atelier/ProjectSwitcher";
import { ThemeToggle } from "../atelier/ThemeToggle";
import { Drawer } from "../ui/Drawer";
import { useAuth } from "../../contexts/auth";
import { PersistentOutletProvider } from "../../hooks/PersistentOutletProvider";
import { resolveRouteMeta } from "../../lib/routes";
import { UI_COPY } from "../../lib/uiCopy";
import { fadeUpVariants, transition } from "../../lib/motion";
import { getCurrentUserId } from "../../services/currentUser";
import {
  advancedDebugCollapsedStorageKey,
  advancedDebugVisibleStorageKey,
  sidebarCollapsedStorageKey,
} from "../../services/uiState";

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

function useAdvancedDebugVisible(): [boolean, (v: boolean) => void] {
  const storageKey = advancedDebugVisibleStorageKey(getCurrentUserId());
  const [visible, setVisible] = useState<boolean>(() => localStorage.getItem(storageKey) === "1");
  return [
    visible,
    (v) => {
      setVisible(v);
      localStorage.setItem(storageKey, v ? "1" : "0");
    },
  ];
}

function useAdvancedDebugCollapsed(): [boolean, (v: boolean) => void] {
  const storageKey = advancedDebugCollapsedStorageKey(getCurrentUserId());
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    const raw = localStorage.getItem(storageKey);
    return raw === null ? true : raw === "1";
  });
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
  ariaLabel?: string;
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
      aria-label={props.ariaLabel ?? props.label}
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

function SidebarButton(props: {
  icon: React.ReactNode;
  label: string;
  ariaLabel?: string;
  collapsed: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={clsx(
        "ui-focus-ring ui-transition-fast group relative flex w-full items-center overflow-hidden rounded-atelier py-2 text-sm hover:bg-canvas motion-safe:active:scale-[0.99]",
        props.collapsed ? "justify-center px-0" : "justify-start gap-3 px-3",
      )}
      aria-label={props.ariaLabel ?? props.label}
      title={props.collapsed ? props.label : undefined}
      onClick={props.onClick}
      type="button"
    >
      <span className="relative z-10 shrink-0">{props.icon}</span>
      {props.collapsed ? null : <span className="relative z-10 min-w-0 truncate">{props.label}</span>}
    </button>
  );
}

const PERSISTENT_OUTLET_CACHE_MAX_ENTRIES = 3;
const PERSISTENT_OUTLET_CACHE_WHITELIST: RegExp[] = [/^\/projects\/[^/]+\/writing$/];

function isPersistentOutletCacheable(pathname: string): boolean {
  return PERSISTENT_OUTLET_CACHE_WHITELIST.some((pattern) => pattern.test(pathname));
}

type PersistentOutletCacheState = {
  elementsByKey: Map<string, React.ReactNode>;
  lruKeys: string[];
};

function PersistentOutlet(props: { activeKey: string }) {
  const outlet = useOutlet();
  const activeIsCacheable = isPersistentOutletCacheable(props.activeKey);
  const [cacheState, setCacheState] = useState<PersistentOutletCacheState>(() => ({
    elementsByKey: activeIsCacheable ? new Map([[props.activeKey, outlet]]) : new Map(),
    lruKeys: activeIsCacheable ? [props.activeKey] : [],
  }));

  const cacheStateWithActive = useMemo(() => {
    if (!activeIsCacheable) return cacheState;

    let nextElementsByKey = cacheState.elementsByKey;
    let nextLruKeys = cacheState.lruKeys;

    if (!nextElementsByKey.has(props.activeKey)) {
      nextElementsByKey = new Map(nextElementsByKey);
      nextElementsByKey.set(props.activeKey, outlet);
    }

    if (nextLruKeys[nextLruKeys.length - 1] !== props.activeKey) {
      nextLruKeys = nextLruKeys.filter((key) => key !== props.activeKey);
      nextLruKeys.push(props.activeKey);
    }

    while (nextLruKeys.length > PERSISTENT_OUTLET_CACHE_MAX_ENTRIES) {
      const evictedKey = nextLruKeys[0];
      nextLruKeys = nextLruKeys.slice(1);
      if (nextElementsByKey.has(evictedKey)) {
        nextElementsByKey = new Map(nextElementsByKey);
        nextElementsByKey.delete(evictedKey);
      }
    }

    if (nextElementsByKey === cacheState.elementsByKey && nextLruKeys === cacheState.lruKeys) return cacheState;
    return { elementsByKey: nextElementsByKey, lruKeys: nextLruKeys };
  }, [activeIsCacheable, cacheState, outlet, props.activeKey]);

  useEffect(() => {
    if (cacheStateWithActive === cacheState) return;
    const id = window.setTimeout(() => setCacheState(cacheStateWithActive), 0);
    return () => window.clearTimeout(id);
  }, [cacheState, cacheStateWithActive]);

  return (
    <>
      {activeIsCacheable ? null : (
        <div key={props.activeKey}>
          <PersistentOutletProvider outletKey={props.activeKey} activeKey={props.activeKey}>
            {outlet}
          </PersistentOutletProvider>
        </div>
      )}
      {Array.from(cacheStateWithActive.elementsByKey.entries()).map(([key, element]) => (
        <div key={key} style={{ display: key === props.activeKey ? "block" : "none" }}>
          <PersistentOutletProvider outletKey={key} activeKey={props.activeKey}>
            {element}
          </PersistentOutletProvider>
        </div>
      ))}
    </>
  );
}

type ContentContainerProps = {
  children: ReactNode;
  className?: string;
};

export function PaperContent(props: ContentContainerProps) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      className={clsx("mx-auto w-full max-w-4xl", props.className)}
      variants={fadeUpVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={reduceMotion ? { duration: 0.01 } : transition.page}
    >
      {props.children}
    </motion.div>
  );
}

export function ToolContent(props: ContentContainerProps) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      className={clsx("mx-auto w-full max-w-screen-xl", props.className)}
      variants={fadeUpVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={reduceMotion ? { duration: 0.01 } : transition.page}
    >
      {props.children}
    </motion.div>
  );
}

export function AppShell() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useSidebarCollapsed();
  const [advancedDebugVisible, setAdvancedDebugVisible] = useAdvancedDebugVisible();
  const [advancedDebugCollapsed, setAdvancedDebugCollapsed] = useAdvancedDebugCollapsed();
  const [mobileNavOpenForPath, setMobileNavOpenForPath] = useState<string | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const { projectId } = useParams();
  const location = useLocation();
  const reduceMotion = useReducedMotion();

  const pathname = location.pathname;
  const routeMeta = useMemo(() => resolveRouteMeta(pathname), [pathname]);
  const title = routeMeta.title;
  const mainMaxWidth =
    routeMeta.layout === "home" ? "max-w-5xl" : routeMeta.layout === "paper" ? "max-w-4xl" : "max-w-screen-xl";
  const sessionExpireAtText = auth.session?.expireAt ? new Date(auth.session.expireAt * 1000).toLocaleString() : null;
  const mobileNavOpen = mobileNavOpenForPath === pathname;

  const CollapseIcon = collapsed ? PanelLeftOpen : PanelLeftClose;
  const collapseLabel = collapsed ? "展开侧边栏" : "收起侧边栏";

  const openMobileNav = () => setMobileNavOpenForPath(pathname);
  const closeMobileNav = () => setMobileNavOpenForPath(null);
  const openHelp = () => setHelpOpen(true);
  const closeHelp = () => setHelpOpen(false);

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
              aria-label={UI_COPY.nav.navMenu}
            >
              <motion.aside
                className="h-full w-[280px] shrink-0 overflow-x-hidden border-r border-border bg-surface p-4 shadow-sm"
                initial={{ x: -12, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                exit={{ x: -12, opacity: 0 }}
                transition={reduceMotion ? { duration: 0.01 } : transition.base}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="font-content text-lg">{UI_COPY.brand.appName}</div>
                  <button
                    className="btn btn-secondary btn-icon"
                    onClick={closeMobileNav}
                    aria-label={UI_COPY.nav.closeNav}
                    title={UI_COPY.nav.closeNav}
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
                      label={UI_COPY.nav.home}
                      ariaLabel="首页 (nav_home)"
                      to="/"
                      onClick={closeMobileNav}
                    />
                    <SidebarButton
                      collapsed={false}
                      icon={<CircleHelp size={18} />}
                      label={UI_COPY.nav.help}
                      ariaLabel="术语/帮助 (nav_help)"
                      onClick={() => {
                        closeMobileNav();
                        openHelp();
                      }}
                    />
                    <div className="my-2 h-px bg-border" />
                    {projectId ? (
                      <>
                        <div className="px-3 pt-2 text-[11px] font-medium text-subtext">
                          {UI_COPY.nav.groupWorkbench}
                        </div>
                        <SidebarLink
                          collapsed={false}
                          icon={<PenLine size={18} />}
                          label={UI_COPY.nav.writing}
                          ariaLabel="写作 (nav_writing)"
                          to={`/projects/${projectId}/writing`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<TableOfContents size={18} />}
                          label={UI_COPY.nav.outline}
                          ariaLabel="大纲 (nav_outline)"
                          to={`/projects/${projectId}/outline`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<Users size={18} />}
                          label={UI_COPY.nav.characters}
                          ariaLabel="角色卡 (nav_characters)"
                          to={`/projects/${projectId}/characters`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<Globe size={18} />}
                          label={UI_COPY.nav.worldBook}
                          ariaLabel="世界书 (nav_worldbook)"
                          to={`/projects/${projectId}/worldbook`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<Share2 size={18} />}
                          label={UI_COPY.nav.graph}
                          ariaLabel="图谱/关系 (nav_graph)"
                          to={`/projects/${projectId}/graph`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<Table2 size={18} />}
                          label={UI_COPY.nav.numericTables}
                          ariaLabel="数值表格（NumericTables） (nav_numeric_tables)"
                          to={`/projects/${projectId}/numeric-tables`}
                          onClick={closeMobileNav}
                        />

                        <div className="mt-2 px-3 pt-2 text-[11px] font-medium text-subtext">
                          {UI_COPY.nav.groupView}
                        </div>
                        <SidebarLink
                          collapsed={false}
                          icon={<BookText size={18} />}
                          label={UI_COPY.nav.chapterAnalysis}
                          ariaLabel="剧情记忆 (nav_chapter_analysis)"
                          to={`/projects/${projectId}/chapter-analysis`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<BookOpen size={18} />}
                          label={UI_COPY.nav.preview}
                          ariaLabel="预览 (nav_preview)"
                          to={`/projects/${projectId}/preview`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<BookOpenText size={18} />}
                          label={UI_COPY.nav.reader}
                          ariaLabel="阅读 (nav_reader)"
                          to={`/projects/${projectId}/reader`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<FileDown size={18} />}
                          label={UI_COPY.nav.export}
                          ariaLabel="导出 (nav_export)"
                          to={`/projects/${projectId}/export`}
                          onClick={closeMobileNav}
                        />

                        <div className="mt-2 px-3 pt-2 text-[11px] font-medium text-subtext">
                          {UI_COPY.nav.groupAiConfig}
                        </div>
                        <SidebarLink
                          collapsed={false}
                          icon={<Bot size={18} />}
                          label={UI_COPY.nav.prompts}
                          ariaLabel="模型配置 (nav_prompts)"
                          to={`/projects/${projectId}/prompts`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<Sparkles size={18} />}
                          label={UI_COPY.nav.promptStudio}
                          ariaLabel="提示词工作室 (nav_prompt_studio)"
                          to={`/projects/${projectId}/prompt-studio`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<Palette size={18} />}
                          label={UI_COPY.nav.styles}
                          ariaLabel="风格 (nav_styles)"
                          to={`/projects/${projectId}/styles`}
                          onClick={closeMobileNav}
                        />
                        <SidebarLink
                          collapsed={false}
                          icon={<Settings size={18} />}
                          label={UI_COPY.nav.projectSettings}
                          ariaLabel="项目设置 (nav_settings)"
                          to={`/projects/${projectId}/settings`}
                          onClick={closeMobileNav}
                        />

                        <label className="mt-2 flex items-center justify-between gap-2 rounded-atelier border border-border bg-canvas px-3 py-2 text-xs text-subtext">
                          <span>显示高级调试</span>
                          <input
                            className="checkbox"
                            checked={advancedDebugVisible}
                            aria-label="显示高级调试 (toggle_advanced_debug)"
                            onChange={(e) => {
                              const next = e.target.checked;
                              setAdvancedDebugVisible(next);
                              if (next) setAdvancedDebugCollapsed(true);
                            }}
                            type="checkbox"
                          />
                        </label>

                        {advancedDebugVisible ? (
                          <details
                            className="mt-2 rounded-atelier border border-border bg-canvas"
                            open={!advancedDebugCollapsed}
                            onToggle={(e) => {
                              setAdvancedDebugCollapsed(!e.currentTarget.open);
                            }}
                          >
                            <summary className="cursor-pointer select-none px-3 py-2 text-[11px] font-medium text-subtext">
                              {UI_COPY.nav.groupAdvancedDebug}
                            </summary>
                            <div className="flex flex-col gap-1 px-1 pb-2">
                              <SidebarLink
                                collapsed={false}
                                icon={<Database size={18} />}
                                label={UI_COPY.nav.rag}
                                ariaLabel="知识库（RAG） (nav_rag)"
                                to={`/projects/${projectId}/rag`}
                                onClick={closeMobileNav}
                              />
                              <SidebarLink
                                collapsed={false}
                                icon={<BookText size={18} />}
                                label={UI_COPY.nav.search}
                                ariaLabel="搜索引擎 (nav_search)"
                                to={`/projects/${projectId}/search`}
                                onClick={closeMobileNav}
                              />
                              <SidebarLink
                                collapsed={false}
                                icon={<Snowflake size={18} />}
                                label={UI_COPY.nav.fractal}
                                ariaLabel="分形（Fractal） (nav_fractal)"
                                to={`/projects/${projectId}/fractal`}
                                onClick={closeMobileNav}
                              />
                              <SidebarLink
                                collapsed={false}
                                icon={<Table2 size={18} />}
                                label={UI_COPY.nav.structuredMemory}
                                ariaLabel="图谱底座数据 (nav_structured_memory)"
                                to={`/projects/${projectId}/structured-memory`}
                                onClick={closeMobileNav}
                              />
                              <SidebarLink
                                collapsed={false}
                                icon={<ListTodo size={18} />}
                                label={UI_COPY.nav.tasks}
                                ariaLabel="任务中心 (nav_tasks)"
                                to={`/projects/${projectId}/tasks`}
                                onClick={closeMobileNav}
                              />
                            </div>
                          </details>
                        ) : null}
                      </>
                    ) : (
                      <div className="rounded-atelier border border-border bg-canvas p-3 text-xs text-subtext">
                        {UI_COPY.nav.chooseProjectHint}
                      </div>
                    )}
                    <div className="my-2 h-px bg-border" />
                    <div className="px-3 pt-2 text-[11px] font-medium text-subtext">{UI_COPY.nav.groupAdmin}</div>
                    <SidebarLink
                      collapsed={false}
                      icon={<UserCog size={18} />}
                      label={UI_COPY.nav.adminUsers}
                      ariaLabel="用户管理 (nav_admin_users)"
                      to="/admin/users"
                      onClick={closeMobileNav}
                    />
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
            {collapsed ? null : <div className="font-content text-lg">{UI_COPY.brand.appName}</div>}
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
              <SidebarLink
                collapsed={collapsed}
                icon={<LayoutDashboard size={18} />}
                label={UI_COPY.nav.home}
                ariaLabel="首页 (nav_home)"
                to="/"
              />
              <SidebarButton
                collapsed={collapsed}
                icon={<CircleHelp size={18} />}
                label={UI_COPY.nav.help}
                ariaLabel="术语/帮助 (nav_help)"
                onClick={openHelp}
              />
              <div className="my-2 h-px bg-border" />
              {projectId ? (
                <>
                  {collapsed ? null : (
                    <div className="px-3 pt-2 text-[11px] font-medium text-subtext">{UI_COPY.nav.groupWorkbench}</div>
                  )}
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<PenLine size={18} />}
                    label={UI_COPY.nav.writing}
                    ariaLabel="写作 (nav_writing)"
                    to={`/projects/${projectId}/writing`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<TableOfContents size={18} />}
                    label={UI_COPY.nav.outline}
                    ariaLabel="大纲 (nav_outline)"
                    to={`/projects/${projectId}/outline`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<Users size={18} />}
                    label={UI_COPY.nav.characters}
                    ariaLabel="角色卡 (nav_characters)"
                    to={`/projects/${projectId}/characters`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<Globe size={18} />}
                    label={UI_COPY.nav.worldBook}
                    ariaLabel="世界书 (nav_worldbook)"
                    to={`/projects/${projectId}/worldbook`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<Share2 size={18} />}
                    label={UI_COPY.nav.graph}
                    ariaLabel="图谱/关系 (nav_graph)"
                    to={`/projects/${projectId}/graph`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<Table2 size={18} />}
                    label={UI_COPY.nav.numericTables}
                    ariaLabel="数值表格（NumericTables） (nav_numeric_tables)"
                    to={`/projects/${projectId}/numeric-tables`}
                  />

                  {collapsed ? null : (
                    <div className="mt-2 px-3 pt-2 text-[11px] font-medium text-subtext">{UI_COPY.nav.groupView}</div>
                  )}
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<BookText size={18} />}
                    label={UI_COPY.nav.chapterAnalysis}
                    ariaLabel="剧情记忆 (nav_chapter_analysis)"
                    to={`/projects/${projectId}/chapter-analysis`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<BookOpen size={18} />}
                    label={UI_COPY.nav.preview}
                    ariaLabel="预览 (nav_preview)"
                    to={`/projects/${projectId}/preview`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<BookOpenText size={18} />}
                    label={UI_COPY.nav.reader}
                    ariaLabel="阅读 (nav_reader)"
                    to={`/projects/${projectId}/reader`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<FileDown size={18} />}
                    label={UI_COPY.nav.export}
                    ariaLabel="导出 (nav_export)"
                    to={`/projects/${projectId}/export`}
                  />

                  {collapsed ? null : (
                    <div className="mt-2 px-3 pt-2 text-[11px] font-medium text-subtext">
                      {UI_COPY.nav.groupAiConfig}
                    </div>
                  )}
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<Bot size={18} />}
                    label={UI_COPY.nav.prompts}
                    ariaLabel="模型配置 (nav_prompts)"
                    to={`/projects/${projectId}/prompts`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<Sparkles size={18} />}
                    label={UI_COPY.nav.promptStudio}
                    ariaLabel="提示词工作室 (nav_prompt_studio)"
                    to={`/projects/${projectId}/prompt-studio`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<Palette size={18} />}
                    label={UI_COPY.nav.styles}
                    ariaLabel="风格 (nav_styles)"
                    to={`/projects/${projectId}/styles`}
                  />
                  <SidebarLink
                    collapsed={collapsed}
                    icon={<Settings size={18} />}
                    label={UI_COPY.nav.projectSettings}
                    ariaLabel="项目设置 (nav_settings)"
                    to={`/projects/${projectId}/settings`}
                  />

                  {collapsed ? null : (
                    <label className="mt-2 flex items-center justify-between gap-2 rounded-atelier border border-border bg-canvas px-3 py-2 text-xs text-subtext">
                      <span>显示高级调试</span>
                      <input
                        className="checkbox"
                        checked={advancedDebugVisible}
                        aria-label="显示高级调试 (toggle_advanced_debug)"
                        onChange={(e) => {
                          const next = e.target.checked;
                          setAdvancedDebugVisible(next);
                          if (next) setAdvancedDebugCollapsed(true);
                        }}
                        type="checkbox"
                      />
                    </label>
                  )}

                  {advancedDebugVisible ? (
                    collapsed ? (
                      <>
                        <SidebarLink
                          collapsed={collapsed}
                          icon={<Database size={18} />}
                          label={UI_COPY.nav.rag}
                          ariaLabel="知识库（RAG） (nav_rag)"
                          to={`/projects/${projectId}/rag`}
                        />
                        <SidebarLink
                          collapsed={collapsed}
                          icon={<BookText size={18} />}
                          label={UI_COPY.nav.search}
                          ariaLabel="搜索引擎 (nav_search)"
                          to={`/projects/${projectId}/search`}
                        />
                        <SidebarLink
                          collapsed={collapsed}
                          icon={<Snowflake size={18} />}
                          label={UI_COPY.nav.fractal}
                          ariaLabel="分形（Fractal） (nav_fractal)"
                          to={`/projects/${projectId}/fractal`}
                        />
                        <SidebarLink
                          collapsed={collapsed}
                          icon={<Table2 size={18} />}
                          label={UI_COPY.nav.structuredMemory}
                          ariaLabel="图谱底座数据 (nav_structured_memory)"
                          to={`/projects/${projectId}/structured-memory`}
                        />
                        <SidebarLink
                          collapsed={collapsed}
                          icon={<ListTodo size={18} />}
                          label={UI_COPY.nav.tasks}
                          ariaLabel="任务中心 (nav_tasks)"
                          to={`/projects/${projectId}/tasks`}
                        />
                      </>
                    ) : (
                      <details
                        className="mt-2 rounded-atelier border border-border bg-canvas"
                        open={!advancedDebugCollapsed}
                        onToggle={(e) => {
                          setAdvancedDebugCollapsed(!e.currentTarget.open);
                        }}
                      >
                        <summary className="cursor-pointer select-none px-3 py-2 text-[11px] font-medium text-subtext">
                          {UI_COPY.nav.groupAdvancedDebug}
                        </summary>
                        <div className="flex flex-col gap-1 px-1 pb-2">
                          <SidebarLink
                            collapsed={collapsed}
                            icon={<Database size={18} />}
                            label={UI_COPY.nav.rag}
                            ariaLabel="知识库（RAG） (nav_rag)"
                            to={`/projects/${projectId}/rag`}
                          />
                          <SidebarLink
                            collapsed={collapsed}
                            icon={<BookText size={18} />}
                            label={UI_COPY.nav.search}
                            ariaLabel="搜索引擎 (nav_search)"
                            to={`/projects/${projectId}/search`}
                          />
                          <SidebarLink
                            collapsed={collapsed}
                            icon={<Snowflake size={18} />}
                            label={UI_COPY.nav.fractal}
                            ariaLabel="分形（Fractal） (nav_fractal)"
                            to={`/projects/${projectId}/fractal`}
                          />
                          <SidebarLink
                            collapsed={collapsed}
                            icon={<Table2 size={18} />}
                            label={UI_COPY.nav.structuredMemory}
                            ariaLabel="图谱底座数据 (nav_structured_memory)"
                            to={`/projects/${projectId}/structured-memory`}
                          />
                          <SidebarLink
                            collapsed={collapsed}
                            icon={<ListTodo size={18} />}
                            label={UI_COPY.nav.tasks}
                            ariaLabel="任务中心 (nav_tasks)"
                            to={`/projects/${projectId}/tasks`}
                          />
                        </div>
                      </details>
                    )
                  ) : null}
                </>
              ) : (
                <div
                  className={clsx(
                    "rounded-atelier border border-border bg-canvas p-3 text-xs text-subtext",
                    collapsed && "hidden",
                  )}
                >
                  {UI_COPY.nav.chooseProjectHint}
                </div>
              )}
              <div className="my-2 h-px bg-border" />
              {collapsed ? null : (
                <div className="px-3 pt-2 text-[11px] font-medium text-subtext">{UI_COPY.nav.groupAdmin}</div>
              )}
              <SidebarLink
                collapsed={collapsed}
                icon={<UserCog size={18} />}
                label={UI_COPY.nav.adminUsers}
                ariaLabel="用户管理 (nav_admin_users)"
                to="/admin/users"
              />
            </nav>
          </LayoutGroup>
        </aside>

        <main className="flex-1">
          <header className="border-b border-border bg-canvas">
            <div className={clsx("mx-auto px-4 py-5 sm:px-6 sm:py-6 lg:px-8", mainMaxWidth)}>
              <div className="flex items-center justify-between gap-4">
                <div className="flex min-w-0 items-center gap-3">
                  <button
                    className="btn btn-secondary btn-icon lg:hidden"
                    onClick={openMobileNav}
                    aria-label={UI_COPY.nav.openNav}
                    title={UI_COPY.nav.openNav}
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
          <div className={clsx("mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8", mainMaxWidth)}>
            <PersistentOutlet activeKey={pathname} />
          </div>
        </main>
      </div>

      <Drawer
        open={helpOpen}
        onClose={closeHelp}
        ariaLabel={UI_COPY.help.title}
        panelClassName="h-full w-full max-w-xl border-l border-border bg-canvas p-6 shadow-sm"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="font-content text-2xl text-ink">{UI_COPY.help.title}</div>
            <div className="mt-1 text-xs text-subtext">{UI_COPY.help.subtitle}</div>
          </div>
          <button className="btn btn-secondary" aria-label="关闭" onClick={closeHelp} type="button">
            关闭
          </button>
        </div>

        <div className="mt-4 grid gap-4">
          <section className="grid gap-2">
            <div className="text-sm font-semibold text-ink">{UI_COPY.help.termsTitle}</div>
            <div className="grid gap-2">
              {UI_COPY.help.terms.map((t) => (
                <div key={t.label} className="rounded-atelier border border-border bg-surface p-3">
                  <div className="text-sm text-ink">{t.label}</div>
                  <div className="mt-1 text-xs text-subtext">{t.description}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="grid gap-2">
            <div className="text-sm font-semibold text-ink">{UI_COPY.help.tipsTitle}</div>
            <ul className="list-disc pl-5 text-xs text-subtext">
              {UI_COPY.help.tips.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </section>
        </div>
      </Drawer>
    </div>
  );
}
