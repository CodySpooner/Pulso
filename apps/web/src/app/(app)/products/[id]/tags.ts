// The context rail's tag rules, mirroring PUT /v1/products/{id}/tags (DEC-243): trimmed, inner spaces collapsed,
// at most 80 characters and 20 tags, no repeat that differs only in case, sorted case-insensitively.

export const MAX_TAGS = 20;
export const MAX_TAG_LENGTH = 80;

const order = (a: string, b: string) => a.localeCompare(b, "en", { sensitivity: "base" });

/** The tag set with `input` added, or why it can't be. An empty input is a no-op. */
export function addTag(tags: string[], input: string): { tags: string[] } | { error: string } {
  const tag = input.trim().replace(/\s+/g, " ");
  if (!tag) return { tags };
  const same = tags.find((t) => t.toLowerCase() === tag.toLowerCase());
  if (same) return { error: `Already tagged “${same}”.` };
  if (tags.length >= MAX_TAGS) return { error: `${MAX_TAGS} tags at most. Remove one first.` };
  if (tag.length > MAX_TAG_LENGTH) return { error: `Tags are ${MAX_TAG_LENGTH} characters at most.` };
  return { tags: [...tags, tag].sort(order) };
}
