// Auth configuration shared by src/proxy.ts and the UI. Fails closed: missing Clerk keys make Clerk throw,
// and an empty allowlist admits nobody.

/** Pure form of `authBypass`, exported for the fail-closed unit test. */
export function authBypassFrom(nodeEnv: string | undefined, flag: string | undefined): boolean {
  return nodeEnv !== "production" && flag === "1";
}

/**
 * E2E-only switch that runs `next dev` without Clerk so Playwright can drive the shell before Clerk keys
 * exist. Both values are inlined at build time, so a production build compiles this to `false` and no
 * runtime env var can turn auth off.
 */
export const authBypass = authBypassFrom(
  process.env.NODE_ENV,
  process.env.NEXT_PUBLIC_PULSO_E2E_AUTH_BYPASS,
);

/** `PLATFORM_ADMIN_USER_IDS` (comma-separated Clerk user ids, the same list the API uses, DEC-020). */
export function parseAllowlist(raw: string | undefined): Set<string> {
  return new Set((raw ?? "").split(",").map((id) => id.trim()).filter(Boolean));
}

export function isPlatformAdmin(userId: string, raw = process.env.PLATFORM_ADMIN_USER_IDS): boolean {
  return parseAllowlist(raw).has(userId);
}
