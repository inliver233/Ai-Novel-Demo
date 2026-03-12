/* eslint-disable no-console */
const crypto = require("node:crypto");
const http = require("node:http");

const requestStats = {
  embeddings_calls: 0,
  last_embeddings: null,
  rerank_calls: 0,
  last_rerank: null,
};

function resetRequestStats() {
  requestStats.embeddings_calls = 0;
  requestStats.last_embeddings = null;
  requestStats.rerank_calls = 0;
  requestStats.last_rerank = null;
}

function captureEmbeddingsCall(req, body, pathname) {
  const model = typeof body?.model === "string" ? body.model : null;
  const input = body?.input;
  const inputs = Array.isArray(input) ? input : input != null ? [input] : [];
  const hasAuth = typeof req?.headers?.authorization === "string" && req.headers.authorization.trim().length > 0;

  requestStats.embeddings_calls += 1;
  requestStats.last_embeddings = {
    at: new Date().toISOString(),
    path: pathname,
    model,
    inputs_count: inputs.length,
    has_api_key: hasAuth,
  };
}

function captureRerankCall(req, body, pathname) {
  const query = typeof body?.query === "string" ? body.query : null;
  const docs = Array.isArray(body?.documents) ? body.documents : [];
  const model = typeof body?.model === "string" ? body.model : null;
  const hasAuth = typeof req?.headers?.authorization === "string" && req.headers.authorization.trim().length > 0;

  requestStats.rerank_calls += 1;
  requestStats.last_rerank = {
    at: new Date().toISOString(),
    path: pathname,
    query,
    model,
    documents_count: docs.length,
    has_api_key: hasAuth,
  };
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let buf = "";
    req.setEncoding("utf-8");
    req.on("data", (chunk) => (buf += chunk));
    req.on("end", () => {
      if (!buf) return resolve({});
      try {
        resolve(JSON.parse(buf));
      } catch (e) {
        reject(e);
      }
    });
  });
}

function extractTaggedBlock(text, tagName) {
  const safeTag = String(tagName || "").trim();
  if (!safeTag) return "";
  const pattern = new RegExp(`<${safeTag}>([\\s\\S]*?)<\\/${safeTag}>`, "i");
  const match = pattern.exec(String(text ?? ""));
  return match ? match[1].trim() : "";
}

function rewriteTaggedContent(rawContent, variant, all) {
  const raw = String(rawContent ?? "").trim();
  if (!raw) {
    return variant === "post_edit"
      ? "E2E 润色校验：未收到可编辑正文。"
      : "E2E 正文优化校验：未收到可优化正文。";
  }

  const paragraphs = raw
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
  if (paragraphs.length === 0) return raw;

  if (variant === "post_edit") {
    const styleInjected = all.includes("e2e 风格注入");
    paragraphs[0] = `${paragraphs[0]} E2E 润色校验已完成，语气更克制。${styleInjected ? "E2E 风格注入已生效。" : ""}`.trim();
  } else {
    paragraphs[0] = `${paragraphs[0]} E2E 正文优化校验已完成，句式更顺滑。`;
  }

  if (paragraphs.length > 1) {
    paragraphs[1] = paragraphs[1]
      .replace("逐块渲染与解析", "逐块渲染、解析与稳态落盘")
      .replace("多次增量更新发生", "增量更新稳定落地");
  }

  return paragraphs.join("\n\n");
}

function chooseOutputText(payload) {
  const messages = Array.isArray(payload?.messages) ? payload.messages : [];
  const combined = messages
    .map((m) => (m && typeof m === "object" ? String(m.content ?? "") : ""))
    .join("\n");
  const all = combined.toLowerCase();

  if (all.includes("你是小说文本编辑与润色器")) {
    const rewritten = rewriteTaggedContent(extractTaggedBlock(combined, "RAW_CONTENT"), "post_edit", all);
    return `<rewrite>\n${rewritten}\n</rewrite>`;
  }

  if (all.includes("你是小说正文优化器")) {
    const optimized = rewriteTaggedContent(extractTaggedBlock(combined, "content"), "content_optimize", all);
    return `<content>\n${optimized}\n</content>`;
  }

  if (all.includes("<rewrite>")) {
    return ["<rewrite>", "", "这是 **E2E** 重写后的正文。", "", "第二段：用于验证重写结果应用。", "", "</rewrite>"].join("\n");
  }

  if (all.includes("outline_md") && all.includes("\"chapters\"")) {
    return JSON.stringify(
      {
        outline_md: "# 大纲（E2E）\n\n- 这是一个用于自动化测试的生成结果。",
        chapters: [
          { number: 1, title: "第一章：起", beats: ["引子", "冲突出现"] },
          { number: 2, title: "第二章：承", beats: ["误会加深", "转折"] },
          { number: 3, title: "第三章：转", beats: ["高潮", "悬念收束"] },
        ],
      },
      null,
      2,
    );
  }

  if (all.includes("<<<content")) {
    const paragraphs = [];
    paragraphs.push("<<<CONTENT>>>", "");
    paragraphs.push("这是 **E2E** 流式生成的正文段落（1）。", "");
    // Keep the content long enough so the frontend streaming parser flushes multiple times
    // (it keeps a tail buffer to detect markers).
    const maxIdx = all.includes("e2e_long_stream") ? 120 : 18;
    for (let i = 2; i <= maxIdx; i += 1) {
      paragraphs.push(`段落 ${i}：用于验证逐块渲染与解析（E2E）。这是一段较长的文本，用来确保多次增量更新发生。`, "");
    }
    paragraphs.push("<<<SUMMARY>>>", "E2E 章节摘要。", "");
    return paragraphs.join("\n");
  }

  if (all.includes("<plan>")) {
    return "<plan>\n- 规划 A\n- 规划 B\n</plan>";
  }

  if (all.includes("chapter_summary") && all.includes("\"hooks\"")) {
    return JSON.stringify(
      {
        chapter_summary: "这是章节分析摘要（E2E）",
        hooks: [{ excerpt: "…", note: "钩子不错" }],
        foreshadows: [{ excerpt: "E2E FORESHADOW EXCERPT", note: "E2E 伏笔" }],
        plot_points: [],
        suggestions: [],
        overall_notes: "整体节奏 OK。",
      },
      null,
      2,
    );
  }

  if (all.includes("memory_update_v1") || all.includes("<memory_update_input>")) {
    return JSON.stringify(
      {
        title: "E2E Memory Update",
        summary_md: "自动化测试：新增/更新角色实体",
        ops: [
          {
            op: "upsert",
            target_table: "entities",
            after: { entity_type: "character", name: "Alice", summary_md: "E2E 角色", attributes: { age: 18 } },
          },
        ],
      },
      null,
      2,
    );
  }

  if (all.includes("schema: table_update_v1")) {
    const value = all.includes("e2e_table_set_gold_100") ? 100 : 0;
    return JSON.stringify(
      {
        title: "E2E Table Update",
        summary_md: "E2E: update numeric tables",
        ops: [
          {
            op: "upsert",
            table_id: "",
            row_id: null,
            data: { key: "gold", value },
          },
        ],
      },
      null,
      2,
    );
  }

  if (all.includes("worldbook_auto_update_v1")) {
    // Default behavior keeps the existing fail-soft test stable (invalid output => parse_error).
    // Opt-in success path for a dedicated E2E test via a marker in chapter content.
    if (all.includes("e2e_worldbook_success")) {
      return JSON.stringify(
        {
          schema_version: "worldbook_auto_update_v1",
          title: "E2E Worldbook Auto Update",
          summary_md: "E2E: create a deterministic worldbook entry",
          ops: [
            {
              op: "create",
              reason: "E2E marker detected in chapter content",
              entry: {
                title: "E2E 城市：阿卡迪亚",
                content_md: "这是由 **E2E** worldbook_auto_update 创建的条目，用于验证自动更新成功链路。",
                keywords: ["阿卡迪亚", "Arcadia", "E2E 城市"],
                aliases: ["E2E_CITY_ARCADIA"],
                enabled: true,
                constant: false,
                exclude_recursion: false,
                prevent_recursion: false,
                char_limit: 12000,
                priority: "important",
              },
            },
          ],
        },
        null,
        2,
      );
    }
  }

  return "E2E mock response.";
}

function writeJson(res, status, body) {
  const json = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(json),
  });
  res.end(json);
}

function writeSseHeaders(res) {
  res.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
  });
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function makeEmbeddingVector(input, dims = 64) {
  const text = typeof input === "string" ? input : JSON.stringify(input ?? "");
  const hash = crypto.createHash("sha256").update(text).digest();
  const out = [];
  for (let i = 0; i < dims; i += 1) {
    // Map bytes to [-1, 1] floats.
    const b = hash[i % hash.length];
    out.push(((b / 255) - 0.5) * 2);
  }
  return out;
}

async function handleEmbeddings(req, res) {
  const body = await readJson(req);
  const url = new URL(req.url || "/", `http://${req.headers.host || "127.0.0.1"}`);
  captureEmbeddingsCall(req, body, url.pathname);
  const input = body?.input;
  const inputs = Array.isArray(input) ? input : [input];
  const data = inputs.map((v, idx) => ({
    object: "embedding",
    index: idx,
    embedding: makeEmbeddingVector(v, 64),
  }));

  writeJson(res, 200, {
    object: "list",
    data,
    model: body?.model ?? "text-embedding-mock",
    usage: { prompt_tokens: 0, total_tokens: 0 },
  });
}

function makeRerankScore(query, doc, idx) {
  const q = String(query ?? "");
  const d = String(doc ?? "");
  const seed = `${q}\n---\n${d}\n#${idx}`;
  const hash = crypto.createHash("sha256").update(seed).digest();
  const u = hash.readUInt32BE(0);
  return u / 0xffffffff;
}

async function handleRerank(req, res) {
  const body = await readJson(req);
  const url = new URL(req.url || "/", `http://${req.headers.host || "127.0.0.1"}`);
  captureRerankCall(req, body, url.pathname);
  const query = body?.query;
  const docs = body?.documents;
  if (typeof query !== "string" || !Array.isArray(docs)) {
    writeJson(res, 400, { error: "bad_request" });
    return;
  }

  let results;
  if (query.includes("E2E_RERANK_REVERSE")) {
    // Deterministic: reverse by index to make E2E assertions stable.
    results = docs
      .map((_d, idx) => ({ index: idx, score: idx }))
      .sort((a, b) => (b.score !== a.score ? b.score - a.score : a.index - b.index));
  } else {
    results = docs
      .map((d, idx) => ({
        index: idx,
        score: makeRerankScore(query, d, idx),
      }))
      .sort((a, b) => (b.score !== a.score ? b.score - a.score : a.index - b.index));
  }

  writeJson(res, 200, {
    object: "list",
    model: body?.model ?? "rerank-mock",
    results,
  });
}

async function streamOpenAICompat(res, fullText) {
  writeSseHeaders(res);

  // Chunk by small slices to simulate real streaming.
  const chunks = [];
  const size = 12;
  for (let i = 0; i < fullText.length; i += size) chunks.push(fullText.slice(i, i + size));

  for (const chunk of chunks) {
    const payload = {
      id: "chatcmpl-mock",
      object: "chat.completion.chunk",
      choices: [{ delta: { content: chunk }, index: 0, finish_reason: null }],
    };
    res.write(`data: ${JSON.stringify(payload)}\n\n`);
    // eslint-disable-next-line no-await-in-loop
    await sleep(15);
  }

  const finalPayload = {
    id: "chatcmpl-mock",
    object: "chat.completion.chunk",
    choices: [{ delta: {}, index: 0, finish_reason: "stop" }],
  };
  res.write(`data: ${JSON.stringify(finalPayload)}\n\n`);
  res.write("data: [DONE]\n\n");
  res.end();
}

async function handleAnthropicMessages(req, res) {
  const body = await readJson(req);

  const messageObjs = [];
  if (typeof body?.system === "string" && body.system.trim()) messageObjs.push({ content: body.system });
  if (Array.isArray(body?.messages)) {
    for (const m of body.messages) {
      if (m && typeof m === "object" && typeof m.content === "string") messageObjs.push({ content: m.content });
    }
  }
  const content = chooseOutputText({ messages: messageObjs });

  writeJson(res, 200, {
    id: "msg-mock",
    type: "message",
    role: "assistant",
    model: body?.model ?? "claude-mock",
    content: [{ type: "text", text: content }],
    stop_reason: "end_turn",
  });
}

async function handleGeminiGenerateContent(req, res) {
  const body = await readJson(req);
  const messageObjs = [];
  if (body?.systemInstruction && typeof body.systemInstruction === "object") {
    const parts = body.systemInstruction.parts;
    if (Array.isArray(parts)) {
      for (const p of parts) {
        if (p && typeof p === "object" && typeof p.text === "string") messageObjs.push({ content: p.text });
      }
    }
  }
  if (Array.isArray(body?.contents)) {
    for (const c of body.contents) {
      if (!c || typeof c !== "object") continue;
      const parts = c.parts;
      if (!Array.isArray(parts)) continue;
      for (const p of parts) {
        if (p && typeof p === "object" && typeof p.text === "string") messageObjs.push({ content: p.text });
      }
    }
  }
  const content = chooseOutputText({ messages: messageObjs });

  writeJson(res, 200, {
    candidates: [
      {
        content: { role: "model", parts: [{ text: content }] },
        finishReason: "STOP",
      },
    ],
  });
}

async function handleChatCompletions(req, res) {
  const body = await readJson(req);
  const stream = Boolean(body?.stream);
  const content = chooseOutputText(body);

  if (stream) {
    await streamOpenAICompat(res, content);
    return;
  }

  writeJson(res, 200, {
    id: "chatcmpl-mock",
    object: "chat.completion",
    choices: [
      {
        index: 0,
        message: { role: "assistant", content },
        finish_reason: "stop",
      },
    ],
  });
}

const port = Number(process.env.PORT || 4010);
const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url || "/", `http://${req.headers.host || "127.0.0.1"}`);
    if (req.method === "GET" && url.pathname === "/health") {
      writeJson(res, 200, { ok: true });
      return;
    }
    if (req.method === "POST" && url.pathname === "/debug/reset") {
      resetRequestStats();
      writeJson(res, 200, { ok: true });
      return;
    }
    if (req.method === "GET" && url.pathname === "/debug/stats") {
      writeJson(res, 200, {
        ok: true,
        data: {
          embeddings_calls: requestStats.embeddings_calls,
          last_embeddings: requestStats.last_embeddings,
          rerank_calls: requestStats.rerank_calls,
          last_rerank: requestStats.last_rerank,
        },
      });
      return;
    }
    if (req.method === "POST" && url.pathname === "/v1/embeddings") {
      await handleEmbeddings(req, res);
      return;
    }
    if (req.method === "POST" && (url.pathname === "/v1/rerank" || url.pathname === "/rerank")) {
      await handleRerank(req, res);
      return;
    }
    if (req.method === "POST" && url.pathname === "/v1/chat/completions") {
      await handleChatCompletions(req, res);
      return;
    }
    if (req.method === "POST" && url.pathname === "/v1/messages") {
      await handleAnthropicMessages(req, res);
      return;
    }
    if (req.method === "POST" && url.pathname.startsWith("/v1beta/models/") && url.pathname.endsWith(":generateContent")) {
      await handleGeminiGenerateContent(req, res);
      return;
    }
    writeJson(res, 404, { error: "not_found" });
  } catch (e) {
    writeJson(res, 500, { error: String(e) });
  }
});

server.listen(port, "127.0.0.1", () => {
  console.log(`[mock-llm] listening on http://127.0.0.1:${port}`);
});
