import { describe, expect, test } from "vitest";

import { attachment, preparing } from "./export-csv";

describe("Discover CSV export", () => {
  test("the button says how many rows once the API has counted", () => {
    expect(preparing(null)).toBe("Preparing export…");
    expect(preparing(1)).toBe("Preparing 1 row…");
    expect(preparing(3412)).toBe("Preparing 3,412 rows…");
  });

  test("the file keeps the API's name", () => {
    expect(attachment('attachment; filename="pulso_discover_2026-10-25.csv"')).toBe("pulso_discover_2026-10-25.csv");
    expect(attachment(null)).toBeNull();
    expect(attachment("inline")).toBeNull();
  });
});
