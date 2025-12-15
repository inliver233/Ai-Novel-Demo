import { Moon, Sun } from "lucide-react";
import { useMemo, useState } from "react";

import { readThemeState, writeThemeState } from "../../services/theme";

export function ThemeToggle() {
  const initial = useMemo(() => readThemeState()?.mode ?? (document.documentElement.classList.contains("dark") ? "dark" : "light"), []);
  const [mode, setMode] = useState<"light" | "dark">(initial);

  const Icon = mode === "dark" ? Sun : Moon;
  const label = mode === "dark" ? "切换到亮色" : "切换到暗色";

  return (
    <button
      className="rounded-atelier border border-border bg-surface px-2 py-2 text-ink hover:bg-canvas"
      onClick={() => {
        const next = mode === "dark" ? "light" : "dark";
        setMode(next);
        writeThemeState({ themeId: "paper-ink", mode: next });
      }}
      title={label}
      type="button"
    >
      <Icon size={18} />
    </button>
  );
}

