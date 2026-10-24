import { onlineManager, QueryClient } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";

import { queryClientConfig } from "./providers";

afterEach(() => onlineManager.setOnline(true));

// imp-134 (aud-014 A14-03): under TanStack's default networkMode an offline mutation pauses, and the client resumes
// it on reconnect, after its dialog was cancelled. Under this config it fails at once and is never sent again.
it("fails an offline mutation at once and never resumes it on reconnect", async () => {
  const client = new QueryClient(queryClientConfig);
  onlineManager.setOnline(false);
  const send = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
  await expect(client.getMutationCache().build(client, { mutationFn: send }).execute(undefined)).rejects.toThrow("Failed to fetch");

  onlineManager.setOnline(true);
  await client.resumePausedMutations();
  expect(send).toHaveBeenCalledTimes(1);
});
