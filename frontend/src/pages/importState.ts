export type ImportDocument = {
  id: string;
  project_id: string;
  actor_user_id: string | null;
  filename: string;
  content_type: string;
  status: string;
  progress: number;
  progress_message: string | null;
  chunk_count: number;
  kb_id: string | null;
  error_message: string | null;
  created_at: string | null;
  updated_at: string | null;
};

function parseIso(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function statusRank(status: string | null | undefined): number {
  const normalized = String(status || "")
    .trim()
    .toLowerCase();
  if (normalized === "done") return 4;
  if (normalized === "failed") return 3;
  if (normalized === "running") return 2;
  if (normalized === "queued") return 1;
  return 0;
}

function preferImportDocument(current: ImportDocument, candidate: ImportDocument): ImportDocument {
  const currentUpdated = parseIso(current.updated_at) ?? parseIso(current.created_at) ?? Number.NEGATIVE_INFINITY;
  const candidateUpdated = parseIso(candidate.updated_at) ?? parseIso(candidate.created_at) ?? Number.NEGATIVE_INFINITY;
  if (candidateUpdated !== currentUpdated) return candidateUpdated > currentUpdated ? candidate : current;

  const currentStatus = statusRank(current.status);
  const candidateStatus = statusRank(candidate.status);
  if (candidateStatus !== currentStatus) return candidateStatus > currentStatus ? candidate : current;

  const currentProgress = Number.isFinite(current.progress) ? current.progress : 0;
  const candidateProgress = Number.isFinite(candidate.progress) ? candidate.progress : 0;
  if (candidateProgress !== currentProgress) return candidateProgress > currentProgress ? candidate : current;

  return candidate;
}

export function mergeImportDocuments(
  current: ImportDocument[],
  incoming: ImportDocument[],
  pinned: ImportDocument[] = [],
): ImportDocument[] {
  const merged = new Map<string, ImportDocument>();
  for (const document of current) {
    if (document?.id) merged.set(document.id, document);
  }
  for (const document of incoming) {
    if (!document?.id) continue;
    const existing = merged.get(document.id);
    merged.set(document.id, existing ? preferImportDocument(existing, document) : document);
  }
  for (const document of pinned) {
    if (!document?.id) continue;
    const existing = merged.get(document.id);
    merged.set(document.id, existing ? preferImportDocument(existing, document) : document);
  }

  return Array.from(merged.values()).sort((left, right) => {
    const rightTime = parseIso(right.updated_at) ?? parseIso(right.created_at) ?? Number.NEGATIVE_INFINITY;
    const leftTime = parseIso(left.updated_at) ?? parseIso(left.created_at) ?? Number.NEGATIVE_INFINITY;
    if (rightTime !== leftTime) return rightTime - leftTime;
    return right.id.localeCompare(left.id);
  });
}

export function getImportProposalDisabledReason(status: string | null | undefined): string | null {
  const normalized = String(status || "")
    .trim()
    .toLowerCase();
  if (!normalized) return "请先选择一条导入记录。";
  if (normalized === "done") return null;
  if (normalized === "queued" || normalized === "running") return "导入完成后才能应用提案。";
  if (normalized === "failed") return "导入失败后不能应用提案，请先重试。";
  return `当前状态“${status}”暂不支持应用提案。`;
}
