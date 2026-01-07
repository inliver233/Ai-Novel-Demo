import type { BrowserContext, Route } from "@playwright/test";

type NetworkGuardOptions = {
  allowedHosts?: string[];
};

const DEFAULT_ALLOWED_HOSTS = ["127.0.0.1", "localhost", "::1"];
const ALLOWED_SCHEMES_WITHOUT_HOST = new Set(["data:", "blob:", "about:"]);

function isAllowedUrl(rawUrl: string, allowedHosts: Set<string>): { ok: true } | { ok: false; host: string } {
  const parsed = new URL(rawUrl);
  if (ALLOWED_SCHEMES_WITHOUT_HOST.has(parsed.protocol)) return { ok: true };

  const host = parsed.hostname;
  if (allowedHosts.has(host)) return { ok: true };
  return { ok: false, host };
}

export async function installNetworkEgressGuard(context: BrowserContext, opts: NetworkGuardOptions = {}): Promise<void> {
  const allowedHosts = new Set(opts.allowedHosts ?? DEFAULT_ALLOWED_HOSTS);
  await context.route("**/*", async (route: Route) => {
    const requestUrl = route.request().url();
    let allowed: ReturnType<typeof isAllowedUrl>;
    try {
      allowed = isAllowedUrl(requestUrl, allowedHosts);
    } catch {
      // If URL parsing fails for any reason, do not block (avoid false positives).
      await route.continue();
      return;
    }

    if (allowed.ok) {
      await route.continue();
      return;
    }

    await route.abort();
    throw new Error(
      `[network-guard] Blocked non-local browser request to host="${allowed.host}": ${requestUrl}\n` +
        `Only localhost loopback hosts are allowed in UI tests.`,
    );
  });
}

