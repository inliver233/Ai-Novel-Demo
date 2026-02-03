import clsx from "clsx";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useRef } from "react";

import { overlayFadeVariants, transition } from "../../lib/motion";

type EscCloseHandler = () => void;

function _escStack(): EscCloseHandler[] {
  if (typeof window === "undefined") return [];
  const w = window as unknown as { __ainovelOverlayEscStack?: EscCloseHandler[] };
  if (!w.__ainovelOverlayEscStack) w.__ainovelOverlayEscStack = [];
  return w.__ainovelOverlayEscStack;
}

function _ensureEscListener() {
  if (typeof window === "undefined") return;
  const w = window as unknown as { __ainovelOverlayEscListenerAttached?: boolean };
  if (w.__ainovelOverlayEscListenerAttached) return;
  w.__ainovelOverlayEscListenerAttached = true;

  window.addEventListener("keydown", (e: KeyboardEvent) => {
    if (e.key !== "Escape") return;
    if (e.defaultPrevented) return;
    const stack = _escStack();
    const handler = stack[stack.length - 1];
    if (!handler) return;
    e.preventDefault();
    handler();
  });
}

export function Overlay(props: {
  open: boolean;
  className?: string;
  children: React.ReactNode;
  onBackdropClick?: () => void;
}) {
  const reduceMotion = useReducedMotion();
  const closeRef = useRef(props.onBackdropClick);

  useEffect(() => {
    closeRef.current = props.onBackdropClick;
  }, [props.onBackdropClick]);

  useEffect(() => {
    _ensureEscListener();
  }, []);

  useEffect(() => {
    if (!props.open || !props.onBackdropClick) return;
    const handler = () => closeRef.current?.();
    const stack = _escStack();
    stack.push(handler);
    return () => {
      const nextStack = _escStack();
      const idx = nextStack.lastIndexOf(handler);
      if (idx >= 0) nextStack.splice(idx, 1);
    };
  }, [props.open, props.onBackdropClick]);

  return (
    <AnimatePresence>
      {props.open ? (
        <motion.div
          className={clsx("fixed inset-0 z-50 bg-black/30", props.className)}
          initial="initial"
          animate="animate"
          exit="exit"
          variants={overlayFadeVariants}
          transition={reduceMotion ? { duration: 0.01 } : transition.base}
          onPointerDown={(e) => {
            if (!props.onBackdropClick) return;
            if (e.target !== e.currentTarget) return;
            props.onBackdropClick();
          }}
        >
          {props.children}
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
