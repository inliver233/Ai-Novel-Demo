import { copyText } from "../../../lib/copyText";

export async function writeClipboardText(text: string): Promise<void> {
  const ok = await copyText(text, { title: "复制失败：请手动复制" });
  if (!ok) throw new Error("clipboard_unavailable");
}

export function downloadJson(filename: string, value: unknown): void {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
