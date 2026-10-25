import { expect, test } from "vitest";

import { marginFix } from "./overview-model";

test("a withheld margin's one next action follows the gap the card names", () => {
  // Duty is the card's amber label whenever it is a gap, so its action wins, even beside a supplier gap.
  expect(marginFix(["duty_not_set"])).toEqual({ label: "Set duty", href: "/settings#duty" });
  expect(marginFix(["supplier_cost_missing", "duty_not_set"])).toEqual({ label: "Set duty", href: "/settings#duty" });
  // No settings row yet: Settings' first read creates it.
  expect(marginFix([])).toEqual({ label: "Open Settings", href: "/settings" });
  // A missing supplier or quote beats a missing price: Profit has nothing to cost without a supplier.
  expect(marginFix(["price_missing", "supplier_cost_missing", "freight_missing"])).toEqual({ label: "Open Suppliers", tab: "suppliers" });
  expect(marginFix(["freight_variant_mismatch"])).toEqual({ label: "Open Suppliers", tab: "suppliers" });
  expect(marginFix(["price_missing"])).toEqual({ label: "Enter a price", tab: "profit" });
  expect(marginFix(["fx_missing"])).toEqual({ label: "Open Profit", tab: "profit" });
  expect(marginFix(["amount_out_of_range"])).toEqual({ label: "Open Profit", tab: "profit" });
});
