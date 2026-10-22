// Motion tokens (vault Design/Motion System). Durations are mirrored as CSS variables in tokens.css.
export const duration = { instant: 0, fast: 0.12, base: 0.2, slow: 0.28, slower: 0.4 } as const; // seconds

export const ease = {
  out: [0.16, 1, 0.3, 1], // entering: fast start, long settle (expo-out)
  in: [0.7, 0, 0.84, 0], // exiting: gets out of the way
  inOut: [0.65, 0, 0.35, 1], // moving between two on-screen positions
  standard: [0.2, 0, 0, 1], // colour and small state changes
} as const;

export const spring = {
  snappy: { type: "spring", visualDuration: 0.2, bounce: 0 }, // tab/nav indicators, switches, segmented thumbs
  smooth: { type: "spring", visualDuration: 0.3, bounce: 0 }, // layout reflow, kanban settle, reorder
  gentle: { type: "spring", visualDuration: 0.4, bounce: 0.1 }, // toasts, empty-state reveal; the only bounce allowed
} as const;

export const stagger = { step: 0.04, max: 6 } as const; // 40ms per item, first 6 items only
