import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { parseEnv } from "node:util";

/**
 * A Playwright server port unique to this checkout: its WEB_PORT plus `offset`. WEB_PORT comes from the shell,
 * else the repo-root .env.local (3000 + slot, which infra/scripts/worktree_env.py writes), else 3000 (the main
 * checkout or CI), the same order as scripts/dev.mjs. Parallel worktrees then never start, or test, each
 * other's server (review P0-08b #2). To run on a free port without an env file (imp-599), set WEB_PORT in the
 * shell: `$env:WEB_PORT=3189; pnpm --filter web e2e` serves on 3289.
 * The configs' webServer.env WEB_PORT (the final port) is never read back and offset twice: Playwright gives it
 * only to the server process, and test workers fork with the runner's env.
 */
export function smokePort(offset: number): number {
  const file = path.join(__dirname, "../../../.env.local");
  const webPort = process.env.WEB_PORT ?? (existsSync(file) ? parseEnv(readFileSync(file, "utf8")).WEB_PORT : undefined);
  return Number(webPort ?? 3000) + offset;
}
