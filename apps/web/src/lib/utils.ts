import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Pulso's type scale names (`text-label`, `text-title-1`, …) are font sizes, not colours. Without this,
// tailwind-merge would treat `text-label text-muted-foreground` as two colours and drop one.
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      text: ["display", "title-1", "title-2", "title-3", "body", "data", "label", "micro", "stat-xl", "stat-lg", "wordmark"],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
