import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "@playwright/test";

import { BOARD, mockBoardsApi } from "./fixtures";

// WF-3d board CSV (imp-456, DEC-350): Export CSV and E on /boards/[id], against the fixture boards API.
const FILE = "pulso_board_q4-gift-ideas_2026-10-25.csv";
const exportButton = (page: Page) => page.getByRole("button", { name: /^(Export CSV|Preparing|Downloaded)/ });
/** The page's CSV requests, by query string. */
function csvRequests(page: Page) {
  const seen: string[] = [];
  page.on("request", (r) => r.url().includes("format=csv") && seen.push(new URL(r.url()).search));
  return seen;
}

test("Export CSV downloads every card in board order, in a file named after the board", async ({ page }) => {
  await mockBoardsApi(page);
  const csv = csvRequests(page);
  await page.goto(`/boards/${BOARD(1)}`);
  await expect(page.getByRole("link", { name: "Sunset projection lamp" })).toBeVisible();
  const download = page.waitForEvent("download");
  await exportButton(page).click(); // 1 click from the board
  const file = await download;
  expect(file.suggestedFilename()).toBe(FILE);
  expect(await readFile((await file.path())!, "utf8")).toBe(
    "﻿position,product\r\n1,Sunset projection lamp\r\n2,Galaxy star projector\r\n3,Mini waffle maker\r\n4,Cloud pillow slides\r\n5,Posture corrector brace\r\n",
  );
  expect(csv).toEqual(["?format=csv"]); // no limit or cursor: the API streams every card, past the 100 shown
  await expect(exportButton(page)).toHaveText("Downloaded");
  await expect(page.getByRole("status").filter({ hasText: `Downloaded ${FILE}` })).toBeAttached();
});

test("E exports while focus is on the cards, never from a note or a card's menu", async ({ page }) => {
  await mockBoardsApi(page);
  const csv = csvRequests(page);
  await page.goto(`/boards/${BOARD(1)}`);
  await expect(exportButton(page)).toHaveAttribute("aria-keyshortcuts", "E");
  await page.getByRole("textbox", { name: "Note on Galaxy star projector" }).press("e"); // typing a note
  await page.getByRole("button", { name: "More for Galaxy star projector" }).press("Enter");
  await expect(page.getByRole("menu")).toBeVisible();
  await page.keyboard.press("e"); // the menu's typeahead
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toBeHidden();
  expect(csv).toEqual([]);

  await page.getByRole("link", { name: "Sunset projection lamp" }).focus();
  const download = page.waitForEvent("download");
  await page.keyboard.press("e");
  expect((await download).suggestedFilename()).toBe(FILE);
  expect(csv).toEqual(["?format=csv"]);
});
