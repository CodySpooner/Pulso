import { describe, expect, test } from "vitest";

import { OFFLINE_HINT } from "@/components/shell/offline-banner";

import { runBlocker } from "./model";

const OFF_HOST = "Live collectors run only on the collector host.";
const DISABLED = "Enable the source before running it.";
const allowed = { live_runs_allowed: true };
const disallowed = { live_runs_allowed: false };

describe("runBlocker", () => {
  test.each([
    ["all clear", allowed, true, true, null],
    ["the host disallows live runs", disallowed, true, true, OFF_HOST],
    ["the host is unknown (loading or failed): no host reason", undefined, true, true, null],
    ["the source is disabled", allowed, false, true, DISABLED],
    ["offline", allowed, true, false, OFFLINE_HINT],
    // Order when several hold: host, then enabled, then offline last (the others still hold once reconnected).
    ["host and disabled: the host first", disallowed, false, true, OFF_HOST],
    ["host and offline: the host first", disallowed, true, false, OFF_HOST],
    ["disabled and offline: disabled first", allowed, false, false, DISABLED],
    ["all three: the host first", disallowed, false, false, OFF_HOST],
    ["unknown host, disabled and offline: disabled first", undefined, false, false, DISABLED],
    ["unknown host and offline", undefined, true, false, OFFLINE_HINT],
  ])("%s", (_, host, enabled, online, reason) => {
    expect(runBlocker(host, { enabled }, online)).toBe(reason);
  });
});
