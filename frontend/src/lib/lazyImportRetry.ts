const CHUNK_RELOAD_MARK_KEY = "ainovel:chunk-reload-mark";
const CHUNK_RELOAD_TTL_MS = 60 * 1000;

type ChunkReloadMark = {
  at: number;
  href: string;
};

function readReloadMark(): ChunkReloadMark | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(CHUNK_RELOAD_MARK_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ChunkReloadMark;
    if (!parsed || typeof parsed.at !== "number" || typeof parsed.href !== "string") return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeReloadMark(mark: ChunkReloadMark): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(CHUNK_RELOAD_MARK_KEY, JSON.stringify(mark));
  } catch {
    // ignore write failures (private mode/storage disabled).
  }
}

function clearReloadMark(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(CHUNK_RELOAD_MARK_KEY);
  } catch {
    // ignore clear failures (private mode/storage disabled).
  }
}

function errorText(error: unknown): string {
  if (error instanceof Error) {
    return `${error.name}: ${error.message}`;
  }
  return String(error ?? "");
}

export function isChunkLoadError(error: unknown): boolean {
  const text = errorText(error).toLowerCase();
  return (
    text.includes("failed to fetch dynamically imported module") ||
    text.includes("importing a module script failed") ||
    text.includes("chunkloaderror") ||
    (text.includes("loading chunk") && text.includes("failed"))
  );
}

function shouldReloadOnceForChunkError(currentHref: string): boolean {
  const mark = readReloadMark();
  if (!mark) return true;
  const now = Date.now();
  const expired = now - mark.at > CHUNK_RELOAD_TTL_MS;
  const differentPage = mark.href !== currentHref;
  return expired || differentPage;
}

function buildReloadHref(currentHref: string): string {
  const url = new URL(currentHref);
  url.searchParams.set("_chunk_reload", String(Date.now()));
  return url.toString();
}

export async function importWithChunkRetry<TModule>(importer: () => Promise<TModule>): Promise<TModule> {
  try {
    const mod = await importer();
    clearReloadMark();
    return mod;
  } catch (error) {
    if (typeof window !== "undefined" && isChunkLoadError(error)) {
      const currentHref = window.location.href;
      if (shouldReloadOnceForChunkError(currentHref)) {
        writeReloadMark({ at: Date.now(), href: currentHref });
        window.location.replace(buildReloadHref(currentHref));
        return new Promise<TModule>(() => {
          // Keep React.lazy pending while browser navigates away.
        });
      }
      clearReloadMark();
    }
    throw error;
  }
}
