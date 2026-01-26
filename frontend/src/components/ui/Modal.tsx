import clsx from "clsx";
import { motion, useReducedMotion } from "framer-motion";

import { transition } from "../../lib/motion";
import { Overlay } from "./Overlay";

export function Modal(props: {
  open: boolean;
  onClose?: () => void;
  className?: string;
  panelClassName?: string;
  ariaLabel?: string;
  ariaLabelledBy?: string;
  children: React.ReactNode;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <Overlay
      open={props.open}
      onBackdropClick={props.onClose}
      className={clsx("flex items-center justify-center p-4", props.className)}
    >
      <motion.div
        className={clsx("w-full max-h-[calc(100dvh-2rem)] overflow-y-auto overscroll-contain", props.panelClassName)}
        role="dialog"
        aria-modal="true"
        aria-label={props.ariaLabelledBy ? undefined : props.ariaLabel}
        aria-labelledby={props.ariaLabelledBy}
        initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 10, scale: 0.98 }}
        animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
        exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 10, scale: 0.98 }}
        transition={reduceMotion ? { duration: 0.01 } : transition.slow}
      >
        {props.children}
      </motion.div>
    </Overlay>
  );
}
