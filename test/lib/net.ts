import net from "node:net";

export async function getFreePort(host = "127.0.0.1"): Promise<number> {
  return await new Promise<number>((resolve, reject) => {
    const server = net.createServer();
    server.once("error", (err) => reject(err));
    server.listen(0, host, () => {
      const addr = server.address();
      if (!addr || typeof addr === "string") {
        server.close(() => reject(new Error("Failed to resolve assigned port")));
        return;
      }
      const port = Number(addr.port);
      server.close(() => resolve(port));
    });
  });
}

type AssertPortFreeOptions = {
  retries?: number;
  intervalMs?: number;
  hint?: string;
};

export async function assertPortFree(port: number, host = "127.0.0.1", opts?: AssertPortFreeOptions): Promise<void> {
  const retries = Math.max(0, Number(opts?.retries ?? 0));
  const intervalMs = Math.max(50, Number(opts?.intervalMs ?? 250));

  let lastErr: unknown = null;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      await new Promise<void>((resolve, reject) => {
        const server = net.createServer();
        server.once("error", (err) => reject(err));
        server.listen(port, host, () => {
          server.close(() => resolve());
        });
      });
      return;
    } catch (err) {
      lastErr = err;
      if (attempt >= retries) break;
      await new Promise((r) => setTimeout(r, intervalMs));
    }
  }

  const hint = String(opts?.hint || "").trim();
  throw new Error(
    [
      `Port ${host}:${port} is not available${retries ? ` after ${retries + 1} attempts` : ""}.`,
      hint ? `\n${hint}` : "",
      `\n${String(lastErr)}`,
    ].join(""),
  );
}

export async function waitForHttpOk(url: string, opts?: { timeoutMs?: number; intervalMs?: number }): Promise<void> {
  const timeoutMs = opts?.timeoutMs ?? 60_000;
  const intervalMs = opts?.intervalMs ?? 500;
  const start = Date.now();
  // eslint-disable-next-line no-constant-condition
  while (true) {
    try {
      const res = await fetch(url, { method: "GET" });
      if (res.ok) return;
    } catch {
      // ignore
    }
    if (Date.now() - start > timeoutMs) {
      throw new Error(`Timed out waiting for HTTP 200 at: ${url}`);
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}
