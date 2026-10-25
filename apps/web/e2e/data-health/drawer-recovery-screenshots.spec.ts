import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi, offlineNetwork, problem, sources } from "./fixtures";

// imp-136 + imp-179 owner review screenshots from fixtures only: the runs list's footer (Load older runs, and an
// older page that failed, with Retry focused, and the same Retry offline with its reason open below), and a targets
// Retry that restored the targets (the region focused).
// 1440px and 375px, dark and light.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/drawer-recovery`; output goes to docs/screenshots/imp-136/.
const OUT = "../../docs/screenshots/imp-136";
const CJ_RUNS = (url: URL) => url.pathname === "/api/v1/admin/runs" && url.searchParams.get("source") === "cj";
const cjRun = sources.find((s) => s.key === "cj")!.last_run!;
const cjRuns = Array.from({ length: 45 }, (_, i) => ({ ...cjRun, id: cjRun.id - i })); // pages of 20, 20 and 5

async function open(page: Page, width: number, height: number, theme: string) {
  await mockAdminApi(page);
  await page.setViewportSize({ width, height });
  await page.emulateMedia({ colorScheme: theme as "dark" | "light" });
  await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
}

async function openCj(page: Page) {
  await page.goto("/admin/data-health");
  await page.getByRole("button", { name: "CJ Dropshipping: open runs" }).locator("visible=true").click();
  return page.getByRole("dialog", { name: "CJ Dropshipping" });
}

/** CJ's runs in pages; every older page answers 503 while `failing` holds. */
async function pagedRuns(page: Page, failing: boolean) {
  await page.route(CJ_RUNS, (route) => {
    const url = new URL(route.request().url());
    if (failing && url.searchParams.get("cursor")) return route.fulfill({ status: 503, json: problem(503, "req-7f3a") });
    const cursor = Number(url.searchParams.get("cursor") ?? Infinity);
    const rest = cjRuns.filter((r) => r.id < cursor);
    const items = rest.slice(0, Number(url.searchParams.get("limit")));
    return route.fulfill({ json: { items, next_cursor: rest.length > items.length ? items.at(-1)!.id : null } });
  });
}

async function shoot(page: Page, name: string) {
  await page.mouse.move(0, 0); // no hover row from the click that opened the drawer
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/${name}.png` });
}

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    for (const state of ["", "failed", "offline"] as const) {
      test(`drawer older runs${state && ` ${state}`} ${width}px ${theme}`, async ({ page, context }) => {
        await open(page, width, height, theme);
        await pagedRuns(page, state !== "");
        const { setOffline } = await offlineNetwork(page, context);
        const drawer = await openCj(page);
        const more = drawer.getByRole("button", { name: "Load older runs" });
        await more.focus();
        await page.keyboard.press("Shift"); // a key press: the keyboard focus ring shows, as after Tab
        if (state) {
          await page.keyboard.press("Enter");
          await expect(drawer.getByRole("button", { name: "Retry" })).toBeFocused();
          await expect(drawer).toContainText("Couldn't load older runs.");
        }
        if (state === "offline") {
          await setOffline(true);
          await page.keyboard.press("Enter"); // locked: the press shows why (DEC-236 d)
          await expect(page.locator('[role="tooltip"][data-state$="-open"]')).toHaveCount(1);
        }
        await shoot(page, `drawer-older-runs${state && `-${state}`}-${width}-${theme}`);
      });
    }

    test(`drawer targets Retry restored ${width}px ${theme}`, async ({ page }) => {
      await open(page, width, height, theme);
      const api = { down: true };
      await page.route("**/api/v1/admin/runs/418", (route) => (api.down ? route.fulfill({ status: 503, json: problem(503, "req-7f3a") }) : route.fallback()));
      const drawer = await openCj(page);
      await drawer.getByRole("button", { name: "Retry" }).focus();
      api.down = false;
      await page.keyboard.press("Enter");
      await expect(drawer.getByRole("region", { name: "Run 418 targets" })).toBeFocused();
      await shoot(page, `drawer-targets-retry-restored-${width}-${theme}`);
    });
  }
}
