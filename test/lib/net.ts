import net from "node:net";

export async function assertPortFree(port: number, host = "127.0.0.1"): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const server = net.createServer();
    server.once("error", (err) => reject(err));
    server.listen(port, host, () => {
      server.close(() => resolve());
    });
  }).catch((err) => {
    throw new Error(`Port ${host}:${port} is not available. Please stop the process using it and retry.\n${String(err)}`);
  });
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

