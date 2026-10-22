import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { parseEnv } from "node:util";

/**
 * A Playwright server port unique to this checkout: its WEB_PORT (3000 + slot, which
 * infra/scripts/worktree_env.py writes to the repo-root .env.local; 3000 in the main checkout or CI) plus
 * `offset`. Parallel worktrees then never start, or test, each other's server (review P0-08b #2).
 */
export function smokePort(offset: number): number {
  const file = path.join(__dirname, "../../../.env.local");
  const webPort = existsSync(file) ? parseEnv(readFileSync(file, "utf8")).WEB_PORT : undefined;
  return Number(webPort ?? 3000) + offset;
}
