import { Moon, Sun } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useMemo, useState } from "react";

import { transition } from "../../lib/motion";
import { readThemeState, writeThemeState } from "../../services/theme";

export function ThemeToggle() {
  const initial = useMemo(
    () => readThemeState()?.mode ?? (document.documentElement.classList.contains("dark") ? "dark" : "light"),
    [],
  );
  const [mode, setMode] = useState<"light" | "dark">(initial);
  const reduceMotion = useReducedMotion();

  const Icon = mode === "dark" ? Sun : Moon;
  const label = mode === "dark" ? "切换到亮色" : "切换到暗色";

  return (
    <button
      className="btn btn-secondary btn-icon"
      onClick={() => {
        const next = mode === "dark" ? "light" : "dark";
        setMode(next);
        writeThemeState({ themeId: "paper-ink", mode: next });
      }}
      aria-label={label}
      title={label}
      type="button"
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={mode}
          className="inline-flex"
          initial={reduceMotion ? { opacity: 0 } : { opacity: 0, rotate: -90, scale: 0.9 }}
          animate={reduceMotion ? { opacity: 1 } : { opacity: 1, rotate: 0, scale: 1 }}
          exit={reduceMotion ? { opacity: 0 } : { opacity: 0, rotate: 90, scale: 0.9 }}
          transition={reduceMotion ? { duration: 0.01 } : transition.fast}
        >
          <Icon size={18} />
        </motion.span>
      </AnimatePresence>
    </button>
  );
}
