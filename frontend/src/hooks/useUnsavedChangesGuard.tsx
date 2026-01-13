import { useEffect } from "react";
import { useBlocker } from "react-router-dom";

import { useConfirm } from "../components/ui/confirm";

export function UnsavedChangesGuard(props: { when: boolean }) {
  const { confirm } = useConfirm();
  const blocker = useBlocker(props.when);

  useEffect(() => {
    if (blocker.state !== "blocked") return;
    void (async () => {
      const ok = await confirm({
        title: "有未保存修改，确定离开？",
        description: "离开后未保存内容会丢失。",
        confirmText: "离开",
        cancelText: "取消",
        danger: true,
      });
      if (ok) blocker.proceed();
      else blocker.reset();
    })();
  }, [blocker, confirm]);

  useEffect(() => {
    if (!props.when) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [props.when]);

  return null;
}
