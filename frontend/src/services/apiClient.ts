export type ApiErrorPayload = {
  ok: false;
  error: { code: string; message: string; details?: unknown };
  request_id: string;
};

export type ApiOkPayload<T> = {
  ok: true;
  data: T;
  request_id: string;
};

export class ApiError extends Error {
  code: string;
  requestId: string;
  details?: unknown;
  status: number;

  constructor(args: { code: string; message: string; requestId: string; status: number; details?: unknown }) {
    super(args.message);
    this.name = "ApiError";
    this.code = args.code;
    this.requestId = args.requestId;
    this.details = args.details;
    this.status = args.status;
  }
}

async function parseJsonSafe(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { _raw: text };
  }
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<ApiOkPayload<T>> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch (e) {
    throw new ApiError({
      code: "NETWORK_ERROR",
      message: "网络错误，请检查后端是否启动",
      requestId: "unknown",
      status: 0,
      details: e instanceof Error ? e.message : String(e),
    });
  }

  const requestIdHeader = res.headers.get("X-Request-Id") ?? undefined;
  const payload = (await parseJsonSafe(res)) as ApiOkPayload<T> | ApiErrorPayload | unknown;

  if (typeof payload === "object" && payload && "ok" in payload) {
    const typed = payload as ApiOkPayload<T> | ApiErrorPayload;
    if (typed.ok) return typed as ApiOkPayload<T>;
    throw new ApiError({
      code: typed.error.code,
      message: typed.error.message,
      details: typed.error.details,
      requestId: typed.request_id ?? requestIdHeader ?? "unknown",
      status: res.status,
    });
  }

  throw new ApiError({
    code: "DB_ERROR",
    message: "响应格式错误",
    requestId: requestIdHeader ?? "unknown",
    status: res.status,
    details: payload,
  });
}

export async function apiDownloadMarkdown(path: string): Promise<{ filename: string; content: string }> {
  let res: Response;
  try {
    res = await fetch(path);
  } catch (e) {
    throw new ApiError({
      code: "NETWORK_ERROR",
      message: "网络错误，请检查后端是否启动",
      requestId: "unknown",
      status: 0,
      details: e instanceof Error ? e.message : String(e),
    });
  }
  const contentType = res.headers.get("Content-Type") ?? "";
  const requestIdHeader = res.headers.get("X-Request-Id") ?? "unknown";

  if (contentType.includes("text/markdown")) {
    const content = await res.text();
    const cd = res.headers.get("Content-Disposition") ?? "";
    const filename = parseContentDispositionFilename(cd) || "ainovel.md";
    return { filename, content };
  }

  const payload = (await parseJsonSafe(res)) as ApiErrorPayload | unknown;
  if (typeof payload === "object" && payload && "ok" in payload && (payload as ApiErrorPayload).ok === false) {
    const typed = payload as ApiErrorPayload;
    throw new ApiError({
      code: typed.error.code,
      message: typed.error.message,
      details: typed.error.details,
      requestId: typed.request_id ?? requestIdHeader,
      status: res.status,
    });
  }

  throw new ApiError({
    code: "DB_ERROR",
    message: "导出失败",
    requestId: requestIdHeader,
    status: res.status,
    details: payload,
  });
}

function unquoteHeaderValue(value: string): string {
  const trimmed = value.trim();
  if (trimmed.startsWith("\"") && trimmed.endsWith("\"") && trimmed.length >= 2) return trimmed.slice(1, -1);
  return trimmed;
}

function sanitizeFilename(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  const lastSegment = trimmed.split(/[/\\]/).pop() ?? trimmed;
  return lastSegment.replaceAll("\0", "");
}

function parseContentDispositionFilename(header: string): string | null {
  if (!header) return null;

  const filenameStarMatch = /filename\*\s*=\s*([^;]+)/i.exec(header);
  if (filenameStarMatch?.[1]) {
    const raw = unquoteHeaderValue(filenameStarMatch[1]);
    const parts = /^([^']*)'[^']*'(.*)$/.exec(raw);
    const encoded = parts?.[2] ?? raw;
    try {
      const decoded = decodeURIComponent(encoded);
      return sanitizeFilename(decoded) || null;
    } catch {
      return sanitizeFilename(encoded) || null;
    }
  }

  const filenameQuotedMatch = /filename\s*=\s*"([^"]+)"/i.exec(header);
  if (filenameQuotedMatch?.[1]) return sanitizeFilename(filenameQuotedMatch[1]) || null;

  const filenameMatch = /filename\s*=\s*([^;]+)/i.exec(header);
  if (filenameMatch?.[1]) return sanitizeFilename(unquoteHeaderValue(filenameMatch[1])) || null;

  return null;
}
