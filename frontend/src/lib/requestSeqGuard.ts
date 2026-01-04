export type RequestSeqGuard = {
  next: () => number;
  isLatest: (seq: number) => boolean;
  invalidate: () => void;
};

export function createRequestSeqGuard(): RequestSeqGuard {
  let current = 0;
  return {
    next: () => {
      current += 1;
      return current;
    },
    isLatest: (seq: number) => seq === current,
    invalidate: () => {
      current += 1;
    },
  };
}
