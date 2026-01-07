/* eslint-disable no-console */
const http = require("node:http");

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

function chooseOutputText(payload) {
  const messages = Array.isArray(payload?.messages) ? payload.messages : [];
  const all = messages
    .map((m) => (m && typeof m === "object" ? String(m.content ?? "") : ""))
    .join("\n")
    .toLowerCase();

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
        foreshadows: [],
        plot_points: [],
        suggestions: [],
        overall_notes: "整体节奏 OK。",
      },
      null,
      2,
    );
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
