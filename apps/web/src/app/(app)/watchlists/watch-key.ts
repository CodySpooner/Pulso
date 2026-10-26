// W, the ★ key (imp-423): which ★ a keypress toggles, kept out of star.tsx so Vitest covers it without a DOM.

export interface KeyInput {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  repeat: boolean;
  target: EventTarget | null;
}

/** The ★ on the focused product (the card, row or element marked data-product); outside any product, the page's own ★
 *  (data-star="page") on a page that is one product. None while typing, with Ctrl, ⌘ or Alt, held down, on a product
 *  without a ★, or in a dialog or menu, whose letters are its own (a menu's typeahead). */
export function starFor(e: KeyInput, page: Pick<ParentNode, "querySelector">): HTMLElement | null {
  const el = e.target as Partial<HTMLElement> | null;
  if (e.key.toLowerCase() !== "w" || e.ctrlKey || e.metaKey || e.altKey || e.repeat) return null;
  if (el?.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el?.tagName ?? "")) return null;
  const at = el?.closest?.("[data-product], [role=dialog], [role=menu]");
  if (!at) return page.querySelector<HTMLElement>('[data-star="page"]');
  return at.hasAttribute("data-product") ? at.querySelector<HTMLElement>("[data-star]") : null;
}
