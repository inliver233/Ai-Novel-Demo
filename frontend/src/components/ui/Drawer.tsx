import clsx from "clsx";
import { motion, useReducedMotion } from "framer-motion";

import { transition } from "../../lib/motion";
import { Overlay } from "./Overlay";

type Side = "right" | "left" | "bottom";

export function Drawer(props: {
  open: boolean;
  side?: Side;
  onClose?: () => void;
  overlayClassName?: string;
  panelClassName?: string;
  ariaLabel?: string;
  ariaLabelledBy?: string;
  children: React.ReactNode;
}) {
  const reduceMotion = useReducedMotion();
  const side: Side = props.side ?? "right";

  const panelMotion =
    side === "bottom"
      ? {
          initial: reduceMotion ? { opacity: 0 } : { opacity: 0, y: 12 },
          animate: reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 },
          exit: reduceMotion ? { opacity: 0 } : { opacity: 0, y: 12 },
        }
      : side === "left"
        ? {
            initial: reduceMotion ? { opacity: 0 } : { opacity: 0, x: -12 },
            animate: reduceMotion ? { opacity: 1 } : { opacity: 1, x: 0 },
            exit: reduceMotion ? { opacity: 0 } : { opacity: 0, x: -12 },
          }
        : {
            initial: reduceMotion ? { opacity: 0 } : { opacity: 0, x: 12 },
            animate: reduceMotion ? { opacity: 1 } : { opacity: 1, x: 0 },
            exit: reduceMotion ? { opacity: 0 } : { opacity: 0, x: 12 },
          };

  return (
    <Overlay
      open={props.open}
      onBackdropClick={props.onClose}
      className={clsx(
        "flex",
        side === "bottom"
          ? "items-end justify-center sm:items-stretch sm:justify-end"
          : side === "left"
            ? "items-stretch justify-start"
            : "items-stretch justify-end",
        props.overlayClassName,
      )}
    >
      <motion.div
        className={clsx("overflow-y-auto", props.panelClassName)}
        role="dialog"
        aria-modal="true"
        aria-label={props.ariaLabelledBy ? undefined : props.ariaLabel}
        aria-labelledby={props.ariaLabelledBy}
        initial={panelMotion.initial}
        animate={panelMotion.animate}
        exit={panelMotion.exit}
        transition={reduceMotion ? { duration: 0.01 } : transition.slow}
      >
        {props.children}
      </motion.div>
    </Overlay>
  );
}
