import clsx from "clsx";
import { type ReactNode } from "react";

export type BadgeTone = "neutral" | "accent" | "success" | "warning" | "danger" | "info";

const toneClass: Record<BadgeTone, string> = {
  neutral: "bg-canvas text-subtext",
  accent: "bg-accent/10 text-ink",
  success: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  danger: "bg-danger/10 text-danger",
  info: "bg-info/10 text-info",
};

export function Badge(props: { children: ReactNode; tone?: BadgeTone; className?: string }) {
  const tone = props.tone ?? "neutral";
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-atelier px-2 py-0.5 text-[11px]",
        toneClass[tone],
        props.className,
      )}
    >
      {props.children}
    </span>
  );
}
