import { ApiError, type ApiErrorPayload } from "./apiClient";

export type SSEMessage =
  | {
      type: "progress";
      message: string;
      progress: number;
      status: "processing" | "success" | "error";
      word_count?: number;
    }
  | { type: "chunk"; content: string }
  | { type: "result"; data: unknown }
  | { type: "error"; error: string; code?: number }
  | { type: "done" };

export type SSEClientOptions = {
  headers?: Record<string, string>;
  onProgress?: (msg: { message: string; progress: number; status: string; wordCount?: number }) => void;
  onChunk?: (content: string) => void;
  onResult?: (data: unknown) => void;
  onError?: (error: string, code?: number) => void;
  onDone?: () => void;
  onOpen?: (info: { requestId?: string }) => void;
};

export class SSEError extends Error {
  code: string;
  requestId?: string;

  constructor(args: { code: string; message: string; requestId?: string }) {
    super(args.message);
    this.name = "SSEError";
    this.code = args.code;
    this.requestId = args.requestId;
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

function isApiErrorPayload(payload: unknown): payload is ApiErrorPayload {
  if (!payload || typeof payload !== "object") return false;
  return "ok" in payload && (payload as { ok?: unknown }).ok === false;
}

function isAbortError(e: unknown): boolean {
  return typeof e === "object" && e !== null && "name" in e && (e as { name?: unknown }).name === "AbortError";
}

export class SSEPostClient {
  private url: string;
  private data: unknown;
  private options: SSEClientOptions;
  private abortController: AbortController;
  private requestId?: string;
  private accumulatedContent = "";
  private resultData: unknown = undefined;

  constructor(url: string, data: unknown, options: SSEClientOptions = {}) {
    this.url = url;
    this.data = data;
    this.options = options;
    this.abortController = new AbortController();
  }

  abort() {
    this.abortController.abort();
  }

  async connect(): Promise<{ requestId?: string; result?: unknown; accumulatedContent: string }> {
    let response: Response;
    try {
      response = await fetch(this.url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(this.options.headers ?? {}),
        },
        body: JSON.stringify(this.data),
        signal: this.abortController.signal,
      });
    } catch (e: unknown) {
      if (isAbortError(e)) {
        throw new SSEError({ code: "ABORTED", message: "已取消生成" });
      }
      throw new SSEError({ code: "SSE_CONNECTION_ERROR", message: "SSE 连接失败" });
    }

    this.requestId = response.headers.get("X-Request-Id") ?? undefined;
    this.options.onOpen?.({ requestId: this.requestId });

    if (!response.ok) {
      const payload = await parseJsonSafe(response);
      if (isApiErrorPayload(payload)) {
        throw new ApiError({
          code: payload.error.code,
          message: payload.error.message,
          details: payload.error.details,
          requestId: payload.request_id ?? this.requestId ?? "unknown",
          status: response.status,
        });
      }
      throw new SSEError({ code: "SSE_BAD_RESPONSE", message: `HTTP ${response.status}`, requestId: this.requestId });
    }

    const contentType = response.headers.get("Content-Type") ?? "";
    if (!contentType.includes("text/event-stream")) {
      throw new SSEError({ code: "SSE_PROTOCOL_ERROR", message: "响应不是 event-stream", requestId: this.requestId });
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new SSEError({ code: "SSE_STREAM_ERROR", message: "无法获取响应流", requestId: this.requestId });
    }

    const decoder = new TextDecoder();
    let buffer = "";
    let doneReceived = false;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true }).replaceAll("\r", "");

        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";

        for (const block of blocks) {
          const trimmed = block.trim();
          if (!trimmed || trimmed.startsWith(":")) continue;

          let eventType: string | undefined;
          const dataLines: string[] = [];
          for (const line of trimmed.split("\n")) {
            if (line.startsWith("event:")) eventType = line.slice("event:".length).trim();
            if (line.startsWith("data:")) dataLines.push(line.slice("data:".length).trim());
          }
          void eventType;

          if (dataLines.length === 0) continue;
          const dataStr = dataLines.join("\n");

          let msg: SSEMessage;
          try {
            msg = JSON.parse(dataStr) as SSEMessage;
          } catch {
            continue;
          }

          if (msg.type === "progress") {
            this.options.onProgress?.({
              message: msg.message,
              progress: msg.progress,
              status: msg.status,
              wordCount: msg.word_count,
            });
          } else if (msg.type === "chunk") {
            this.accumulatedContent += msg.content;
            this.options.onChunk?.(msg.content);
          } else if (msg.type === "result") {
            this.resultData = msg.data;
            this.options.onResult?.(msg.data);
          } else if (msg.type === "error") {
            this.options.onError?.(msg.error, msg.code);
            throw new SSEError({ code: "SSE_SERVER_ERROR", message: msg.error, requestId: this.requestId });
          } else if (msg.type === "done") {
            doneReceived = true;
            this.options.onDone?.();
            return { requestId: this.requestId, result: this.resultData, accumulatedContent: this.accumulatedContent };
          }
        }
      }
    } catch (e: unknown) {
      if (isAbortError(e)) {
        throw new SSEError({ code: "ABORTED", message: "已取消生成", requestId: this.requestId });
      }
      if (e instanceof SSEError || e instanceof ApiError) {
        throw e;
      }
      throw new SSEError({ code: "SSE_STREAM_ERROR", message: "SSE 读取失败", requestId: this.requestId });
    }

    if (this.abortController.signal.aborted) {
      throw new SSEError({ code: "ABORTED", message: "已取消生成", requestId: this.requestId });
    }
    if (!doneReceived) {
      throw new SSEError({ code: "SSE_EARLY_CLOSE", message: "SSE 连接提前结束", requestId: this.requestId });
    }
    return { requestId: this.requestId, result: this.resultData, accumulatedContent: this.accumulatedContent };
  }
}
