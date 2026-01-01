import clsx from "clsx";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

import { overlayFadeVariants, transition } from "../../lib/motion";

export function Overlay(props: {
  open: boolean;
  className?: string;
  children: React.ReactNode;
  onBackdropClick?: () => void;
}) {
  const reduceMotion = useReducedMotion();

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
