import type { Transition, Variants } from "framer-motion";

export const easeStandard = [0.25, 0.1, 0.25, 1] as const;

export const duration = {
  fast: 0.15,
  base: 0.25,
  slow: 0.35,
  stagger: 0.03,
  page: 0.3,
} as const;

export const transition = {
  fast: { duration: duration.fast, ease: easeStandard } satisfies Transition,
  reduced: { duration: 0.01 } satisfies Transition,
  base: { duration: duration.base, ease: easeStandard } satisfies Transition,
  slow: { duration: duration.slow, ease: easeStandard } satisfies Transition,
  page: { duration: duration.page, ease: easeStandard } satisfies Transition,
} as const;

export const fadeUpVariants: Variants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 10 },
};

export const overlayFadeVariants: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
};
