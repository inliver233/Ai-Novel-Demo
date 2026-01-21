import React from "react";

type DebugPageShellProps = {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
};

export function DebugPageShell(props: DebugPageShellProps) {
  return (
    <div className="grid gap-4">
      <div className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="font-content text-2xl text-ink">{props.title}</div>
            {props.description ? <div className="mt-1 text-xs text-subtext">{props.description}</div> : null}
          </div>
          {props.actions ? <div className="flex flex-wrap items-center gap-2">{props.actions}</div> : null}
        </div>
        <div className="mt-4 grid gap-3">{props.children}</div>
      </div>
    </div>
  );
}

type DebugDetailsProps = {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
};

export function DebugDetails(props: DebugDetailsProps) {
  return (
    <details className="rounded-atelier border border-border bg-canvas p-3" open={props.defaultOpen ? true : undefined}>
      <summary className="cursor-pointer select-none text-xs text-subtext hover:text-ink">{props.title}</summary>
      <div className="mt-2">{props.children}</div>
    </details>
  );
}
