import { pinyin } from "pinyin-pro";

export type PinyinMatchMode = "pinyin_full" | "pinyin_initials";

export type PinyinMatchResult = {
  matched: boolean;
  mode: PinyinMatchMode | null;
};

type PinyinIndex = { full: string; initials: string };

const PINYIN_INDEX_CACHE = new Map<string, PinyinIndex>();

function hasChinese(text: string): boolean {
  return /[\u3400-\u9fff]/.test(text);
}

function normalizeAsciiToken(value: string): string {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

export function tokenizeSearch(value: string): string[] {
  const raw = String(value || "")
    .trim()
    .toLowerCase();
  if (!raw) return [];
  return raw.split(/\s+/g).filter(Boolean);
}

export function looksLikePinyinToken(token: string): boolean {
  return /[a-z]/i.test(token);
}

export function getPinyinIndex(text: string): PinyinIndex | null {
  const key = String(text || "");
  if (!key) return { full: "", initials: "" };
  if (!hasChinese(key)) return null;

  const cached = PINYIN_INDEX_CACHE.get(key);
  if (cached) return cached;

  try {
    const full = normalizeAsciiToken(
      pinyin(key, {
        toneType: "none",
        separator: "",
        nonZh: "removed",
        v: true,
      }),
    );
    const initials = normalizeAsciiToken(
      pinyin(key, {
        toneType: "none",
        pattern: "first",
        separator: "",
        nonZh: "removed",
        v: true,
      }),
    );

    const out = { full, initials };
    PINYIN_INDEX_CACHE.set(key, out);
    return out;
  } catch {
    return null;
  }
}

export function containsPinyinMatch(text: string, token: string): PinyinMatchResult {
  const t = normalizeAsciiToken(token);
  if (!t) return { matched: false, mode: null };

  const idx = getPinyinIndex(text);
  if (!idx) return { matched: false, mode: null };

  if (idx.full.includes(t)) return { matched: true, mode: "pinyin_full" };
  if (idx.initials.includes(t)) return { matched: true, mode: "pinyin_initials" };
  return { matched: false, mode: null };
}
