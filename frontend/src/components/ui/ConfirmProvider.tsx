import React, { useCallback, useMemo, useRef, useState } from "react";

import { Modal } from "./Modal";
import { ConfirmContext } from "./confirm";
import type { ChooseOptions, ConfirmApi, ConfirmChoice, ConfirmOptions } from "./confirm";

export function ConfirmProvider(props: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [variant, setVariant] = useState<"confirm" | "choose">("confirm");
  const [options, setOptions] = useState<ConfirmOptions | ChooseOptions | null>(null);
  const resolverRef = useRef<((value: unknown) => void) | null>(null);

  const confirm = useCallback(async (opts: ConfirmOptions) => {
    setVariant("confirm");
    setOptions(opts);
    setOpen(true);
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve as (value: unknown) => void;
    });
  }, []);

  const choose = useCallback(async (opts: ChooseOptions) => {
    setVariant("choose");
    setOptions(opts);
    setOpen(true);
    return new Promise<ConfirmChoice>((resolve) => {
      resolverRef.current = resolve as (value: unknown) => void;
    });
  }, []);

  const close = useCallback((value: unknown) => {
    setOpen(false);
    const resolve = resolverRef.current;
    resolverRef.current = null;
    resolve?.(value);
    window.setTimeout(() => setOptions(null), 400);
  }, []);

  const api = useMemo<ConfirmApi>(() => ({ confirm, choose }), [choose, confirm]);

  return (
    <ConfirmContext.Provider value={api}>
      {props.children}
      <Modal
        open={open && Boolean(options)}
        onClose={() => close(variant === "choose" ? ("cancel" satisfies ConfirmChoice) : false)}
        panelClassName="surface max-w-md p-5"
        ariaLabel={options?.title ?? "确认"}
      >
        {options ? (
          <>
            <div className="font-content text-xl text-ink">{options.title}</div>
            {options.description ? <div className="mt-2 text-sm text-subtext">{options.description}</div> : null}
            <div className="mt-5 flex justify-end gap-2">
              <button
                className="btn btn-secondary"
                onClick={() => close(variant === "choose" ? ("cancel" satisfies ConfirmChoice) : false)}
                type="button"
              >
                {options.cancelText ?? "取消"}
              </button>
              {variant === "choose" ? (
                <button
                  className={(options as ChooseOptions).secondaryDanger ? "btn btn-danger" : "btn btn-secondary"}
                  onClick={() => close("secondary" satisfies ConfirmChoice)}
                  type="button"
                >
                  {(options as ChooseOptions).secondaryText}
                </button>
              ) : null}
              <button
                className={options.danger ? "btn btn-danger" : "btn btn-primary"}
                onClick={() => close(variant === "choose" ? ("confirm" satisfies ConfirmChoice) : true)}
                type="button"
              >
                {options.confirmText ?? "确认"}
              </button>
            </div>
          </>
        ) : null}
      </Modal>
    </ConfirmContext.Provider>
  );
}
