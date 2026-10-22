// `pnpm dev:web`: starts `next dev` on this worktree's port. infra/scripts/worktree_env.py writes WEB_PORT
// and API_URL to the repo-root .env.local (and the root .env holds PLATFORM_ADMIN_USER_IDS), but Next only
// reads env files from apps/web and reads the port before loading any. Real env vars win over both files.
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parseEnv } from "node:util";

const read = (name) => {
  const file = new URL(`../../../${name}`, import.meta.url);
  return existsSync(file) ? parseEnv(readFileSync(file, "utf8")) : {};
};
const root = { ...read(".env"), ...read(".env.local") };
const pick = (key, fallback) => process.env[key] ?? root[key] ?? fallback;

const env = { ...process.env };
for (const key of ["API_URL", "PLATFORM_ADMIN_USER_IDS"]) {
  const value = pick(key);
  if (value !== undefined) env[key] = value;
}

const next = fileURLToPath(import.meta.resolve("next/dist/bin/next"));
const child = spawn(process.execPath, [next, "dev", "--port", pick("WEB_PORT", "3000"), ...process.argv.slice(2)], {
  stdio: "inherit",
  env,
});
child.on("exit", (code) => process.exit(code ?? 1));
