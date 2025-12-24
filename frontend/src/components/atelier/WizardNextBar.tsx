import clsx from "clsx";
import { ArrowRight, CheckCircle2, Circle, CircleSlash2, ListChecks } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { WizardProgress, WizardStepKey } from "../../services/wizard";

type PrimaryAction = {
  label: string;
  disabled?: boolean;
  onClick: () => Promise<boolean> | boolean | Promise<void> | void;
};

export function WizardNextBar(props: {
  projectId: string | undefined;
  currentStep: WizardStepKey;
  progress: WizardProgress;
  loading?: boolean;
  dirty?: boolean;
  saving?: boolean;
  onSave?: () => Promise<boolean>;
  primaryAction?: PrimaryAction;
}) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  const {
    projectId,
    currentStep,
    progress,
    loading = false,
    dirty = false,
    saving = false,
    onSave,
    primaryAction,
  } = props;

  const current = useMemo(
    () => progress.steps.find((s) => s.key === currentStep) ?? null,
    [currentStep, progress.steps],
  );

  const next = progress.nextStep;
  const previewStep = useMemo(() => progress.steps.find((s) => s.key === "preview") ?? null, [progress.steps]);

  const goto = useCallback(
    (href: string | null | undefined) => {
      if (!href) return;
      navigate(href);
    },
    [navigate],
  );

  const run = useCallback(
    async (fn: () => Promise<boolean> | boolean | Promise<void> | void) => {
      if (busy) return;
      setBusy(true);
      try {
        const res = await fn();
        return res;
      } finally {
        setBusy(false);
      }
    },
    [busy],
  );

  const wizardHref = projectId ? `/projects/${projectId}/wizard` : null;
  const done = !progress.nextStep;
  const showBackToOverview = Boolean(progress.exportedAt && progress.nextStep);

  const primary = useMemo((): PrimaryAction => {
    if (primaryAction) return primaryAction;

    if (dirty && onSave) {
      const target =
        next && next.key !== currentStep
          ? next
          : currentStep === "writing" && next?.key === currentStep
            ? previewStep
            : null;
      const label = target ? `保存并下一步：${target.title}` : "保存";
      return {
        label,
        disabled: Boolean(saving),
        onClick: async () => {
          const ok = await onSave?.();
          if (!ok) return false;
          if (target?.href) goto(target.href);
          return true;
        },
      };
    }

    if (!next) {
      return {
        label: "已完成：回到项目概览",
        onClick: () => goto("/"),
      };
    }

    if (next.key === currentStep) {
      if (currentStep === "writing" && previewStep?.href) {
        return {
          label: `下一步：${previewStep.title}`,
          onClick: () => goto(previewStep.href),
        };
      }
      return {
        label: current ? `本页：${current.title}` : "本页待完成",
        disabled: true,
        onClick: () => {},
      };
    }

    return {
      label: `下一步：${next.title}`,
      onClick: () => goto(next.href),
    };
  }, [current, currentStep, dirty, goto, next, onSave, previewStep, primaryAction, saving]);

  if (!projectId) return null;

  return (
    <div className="sticky bottom-6 z-30 mt-6">
      <div className="rounded-atelier border border-border bg-surface/90 p-4 shadow-sm backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-subtext">
              <span className="inline-flex items-center gap-1">
                <ListChecks size={14} /> 向导 {progress.percent}%
              </span>
              {dirty ? (
                <span className="rounded-atelier bg-accent/10 px-2 py-0.5 text-[11px] text-accent">未保存</span>
              ) : null}
              {done ? (
                <span className="rounded-atelier bg-success/15 px-2 py-0.5 text-[11px] text-success">已完成</span>
              ) : null}
            </div>

            <div className="mt-2 h-2 w-full rounded-full bg-border/60">
              <div
                className="h-2 rounded-full bg-accent motion-safe:transition-[width] motion-safe:duration-atelier motion-safe:ease-atelier"
                style={{ width: `${progress.percent}%` }}
              />
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              {progress.steps.map((s) => {
                const Icon = s.state === "done" ? CheckCircle2 : s.state === "skipped" ? CircleSlash2 : Circle;
                const isCurrent = s.key === currentStep;
                const isNext = progress.nextStep?.key === s.key;
                return (
                  <div
                    key={s.key}
                    className={clsx(
                      "inline-flex items-center gap-1 rounded-atelier border px-2 py-1 text-[11px]",
                      isCurrent ? "border-accent/40 bg-accent/10 text-ink" : "border-border bg-canvas text-subtext",
                      isNext ? "ring-1 ring-accent" : null,
                    )}
                    title={s.description}
                  >
                    <Icon
                      className={clsx(
                        s.state === "done" ? "text-success" : s.state === "skipped" ? "text-subtext" : "text-subtext",
                      )}
                      size={14}
                    />
                    <span className={clsx("max-w-[140px] truncate", isCurrent ? "text-ink" : "text-subtext")}>
                      {s.title}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap gap-2">
            <button
              className="btn btn-secondary"
              disabled={!wizardHref || loading || busy}
              onClick={() => goto(wizardHref)}
              type="button"
            >
              查看向导
            </button>

            {showBackToOverview ? (
              <button className="btn btn-secondary" disabled={loading || busy} onClick={() => goto("/")} type="button">
                已完成：回到项目概览
              </button>
            ) : null}

            <button
              className="btn btn-primary"
              disabled={Boolean(primary.disabled) || loading || busy}
              onClick={() => void run(primary.onClick)}
              type="button"
            >
              <span className="inline-flex items-center gap-2">
                {loading ? "加载中..." : primary.label}
                <ArrowRight size={16} />
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
