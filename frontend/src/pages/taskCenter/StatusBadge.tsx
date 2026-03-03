import { humanizeChangeSetStatus, humanizeTaskStatus } from "../../lib/humanize";

type StatusBadgeProps = {
  status: string;
  kind: "change_set" | "task";
};

function statusTone(status: string): "ok" | "warn" | "bad" | "info" {
  const s = String(status || "").trim();
  if (s === "failed") return "bad";
  if (s === "running") return "warn";
  if (s === "queued" || s === "proposed") return "info";
  return "ok";
}

export function StatusBadge(props: StatusBadgeProps) {
  const tone = statusTone(props.status);
  const cls =
    tone === "bad"
      ? "bg-danger/10 text-danger"
      : tone === "warn"
        ? "bg-warning/10 text-warning"
        : tone === "info"
          ? "bg-info/10 text-info"
          : "bg-success/10 text-success";
  const label = props.kind === "change_set" ? humanizeChangeSetStatus(props.status) : humanizeTaskStatus(props.status);
  return <span className={`inline-flex rounded px-2 py-0.5 text-[11px] ${cls}`}>{label}</span>;
}
