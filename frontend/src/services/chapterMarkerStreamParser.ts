export type ChapterMarkerStreamPhase = "before" | "content" | "summary" | "raw";

export type ChapterMarkerPushResult = {
  phase: ChapterMarkerStreamPhase;
  contentDelta: string;
  summaryDelta: string;
};

export type ChapterMarkerStreamParser = {
  push: (chunk: string) => ChapterMarkerPushResult;
  finalize: () => ChapterMarkerPushResult;
  getPhase: () => ChapterMarkerStreamPhase;
  getBufferLength: () => number;
};

const markerContentRe = /^[ \t]*<<<\s*CONTENT\b\s*(?:>{1,3})?\s*/im;
const markerSummaryRe = /^[ \t]*<<<\s*SUMMARY\b\s*(?:>{1,3})?\s*/im;
const leadingSpaceRe = /^[\s\r\n]+/;

export function createChapterMarkerStreamParser(opts?: {
  maxPreambleChars?: number;
  tailKeepChars?: number;
}): ChapterMarkerStreamParser {
  const maxPreambleChars = opts?.maxPreambleChars ?? 8192;
  const tailKeepChars = opts?.tailKeepChars ?? 256;

  let phase: ChapterMarkerStreamPhase = "before";
  let buffer = "";

  const dropLeadingSpace = (s: string) => s.replace(leadingSpaceRe, "");

  const push = (chunk: string): ChapterMarkerPushResult => {
    buffer += chunk;

    let contentDelta = "";
    let summaryDelta = "";

    while (buffer) {
      if (phase === "before") {
        const m = markerContentRe.exec(buffer);
        if (!m) {
          if (buffer.length > maxPreambleChars) {
            phase = "raw";
            contentDelta += buffer;
            buffer = "";
          }
          break;
        }
        phase = "content";
        buffer = dropLeadingSpace(buffer.slice(m.index + m[0].length));
        continue;
      }

      if (phase === "content") {
        const m = markerSummaryRe.exec(buffer);
        if (!m) {
          if (buffer.length > tailKeepChars) {
            const flushLen = buffer.length - tailKeepChars;
            contentDelta += buffer.slice(0, flushLen);
            buffer = buffer.slice(flushLen);
          }
          break;
        }
        contentDelta += buffer.slice(0, m.index);
        buffer = dropLeadingSpace(buffer.slice(m.index + m[0].length));
        phase = "summary";
        continue;
      }

      if (phase === "summary") {
        summaryDelta += buffer;
        buffer = "";
        break;
      }

      if (phase === "raw") {
        contentDelta += buffer;
        buffer = "";
        break;
      }
    }

    return { phase, contentDelta, summaryDelta };
  };

  const finalize = (): ChapterMarkerPushResult => {
    if (!buffer) return { phase, contentDelta: "", summaryDelta: "" };

    if (phase === "before") {
      phase = "raw";
      const contentDelta = buffer;
      buffer = "";
      return { phase, contentDelta, summaryDelta: "" };
    }
    if (phase === "content") {
      const contentDelta = buffer;
      buffer = "";
      return { phase, contentDelta, summaryDelta: "" };
    }
    if (phase === "summary") {
      const summaryDelta = buffer;
      buffer = "";
      return { phase, contentDelta: "", summaryDelta };
    }
    // raw
    const contentDelta = buffer;
    buffer = "";
    return { phase, contentDelta, summaryDelta: "" };
  };

  return { push, finalize, getPhase: () => phase, getBufferLength: () => buffer.length };
}
