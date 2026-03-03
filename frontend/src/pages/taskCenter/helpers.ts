export function safeJsonStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function extractHowToFix(error: unknown): string[] {
  if (!error || typeof error !== "object") return [];
  const details = (error as Record<string, unknown>).details;
  if (!details || typeof details !== "object") return [];
  const how = (details as Record<string, unknown>).how_to_fix;
  if (!Array.isArray(how)) return [];
  return how.filter((it) => typeof it === "string" && it.trim()).map((it) => it.trim());
}

export function extractRunIdFromProjectTaskError(error: unknown): string | null {
  if (!error || typeof error !== "object") return null;
  const details = (error as Record<string, unknown>).details;
  if (!details || typeof details !== "object") return null;
  const runId = (details as Record<string, unknown>).run_id;
  return typeof runId === "string" && runId.trim() ? runId.trim() : null;
}

export function extractRunIdFromProjectTaskResult(result: unknown): string | null {
  if (!result || typeof result !== "object") return null;
  const runId = (result as Record<string, unknown>).run_id;
  return typeof runId === "string" && runId.trim() ? runId.trim() : null;
}

export function extractChangeSetIdFromProjectTaskResult(result: unknown): string | null {
  if (!result || typeof result !== "object") return null;
  const o = result as Record<string, unknown>;
  const cs = o.change_set;
  if (!cs || typeof cs !== "object") return null;
  const id = (cs as Record<string, unknown>).id;
  return typeof id === "string" && id.trim() ? id.trim() : null;
}

export function extractChangeSetStatusFromProjectTaskResult(result: unknown): string | null {
  if (!result || typeof result !== "object") return null;
  const o = result as Record<string, unknown>;
  const cs = o.change_set;
  if (!cs || typeof cs !== "object") return null;
  const status = (cs as Record<string, unknown>).status;
  return typeof status === "string" && status.trim() ? status.trim() : null;
}
