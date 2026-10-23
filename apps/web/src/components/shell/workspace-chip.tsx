"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";

import { StatusDot } from "@/components/pulso/status-dot";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { $api, isProblem } from "@/lib/api/client";
import { authBypass } from "@/lib/auth";

const chip =
  "relative hit-area hidden h-8 items-center gap-1.5 rounded-md border border-border-subtle px-2 text-label font-medium whitespace-nowrap text-muted-foreground transition-colors duration-(--duration-fast) ease-standard hover:border-border-strong md:inline-flex";

// Top-bar workspace chip: the signed-in user's workspace from GET /v1/me, the first call through the typed
// client (WEB-7). States: loading skeleton, the workspace, "API not reachable" and an API error; the last
// two retry on select. Under the E2E auth bypass there is no Clerk session, so it calls nothing.
export function WorkspaceChip() {
  if (authBypass) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Link href="/settings" className={chip}>
            Workspace <span className="font-mono text-foreground">E2E</span>
          </Link>
        </TooltipTrigger>
        <TooltipContent>Auth is bypassed for end-to-end tests, so the API isn’t called.</TooltipContent>
      </Tooltip>
    );
  }
  return <MeChip />;
}

function MeChip() {
  const { isSignedIn } = useAuth();
  const me = $api.useQuery("get", "/v1/me", {}, { enabled: isSignedIn === true });

  if (me.isPending) return <Skeleton className="hidden h-8 w-36 rounded-md md:block" />;

  if (me.isError) {
    const problem = isProblem(me.error) ? me.error : null;
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <button type="button" className={chip} onClick={() => me.refetch()}>
            <StatusDot state={problem ? "failed" : "warning"} />
            {me.isFetching ? "Checking…" : problem ? "Can’t load workspace" : "API not reachable"}
          </button>
        </TooltipTrigger>
        <TooltipContent className="max-w-64">
          {problem ? (
            <>
              {problem.detail} <span className="font-mono">Request ID {problem.request_id}</span>
            </>
          ) : (
            "The Pulso API didn’t answer at /api. Start it with pnpm dev:api."
          )}{" "}
          Select to retry.
        </TooltipContent>
      </Tooltip>
    );
  }

  const { workspace_id, is_admin } = me.data;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link href="/settings" className={chip}>
          Workspace <span className="font-mono text-foreground">{workspace_id.slice(0, 8)}</span>
        </Link>
      </TooltipTrigger>
      <TooltipContent>
        <span className="font-mono">{workspace_id}</span>
        {is_admin && " · platform admin"}
        <br />
        From /v1/me, checked {new Date(me.dataUpdatedAt).toISOString().slice(11, 16)} UTC
      </TooltipContent>
    </Tooltip>
  );
}
