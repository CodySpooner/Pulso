import type { Metadata } from "next";
import { SignOutButton } from "@clerk/nextjs";
import { auth } from "@clerk/nextjs/server";

import { AuthFrame } from "@/components/pulso/auth-frame";
import { CopyButton } from "@/components/pulso/copy-button";
import { Button } from "@/components/ui/button";
import { authBypass } from "@/lib/auth";

export const metadata: Metadata = { title: "Not authorized" };

// Signed in but not on PLATFORM_ADMIN_USER_IDS (DEC-020). Shows the Clerk user id so the owner can add
// it to the allowlist on first sign-in.
export default async function NotAuthorizedPage() {
  const userId = authBypass ? null : (await auth()).userId;
  return (
    <AuthFrame
      title="This Pulso is private"
      description="Your account isn't on this workspace's allowlist. If this is your Pulso, add your user ID to PLATFORM_ADMIN_USER_IDS and reload."
    >
      {userId && (
        <div className="flex w-full items-center gap-2 rounded-lg border border-border bg-card py-1 pr-1 pl-3 shadow-card">
          <span className="text-label text-subtle-foreground">User ID</span>
          <code className="min-w-0 flex-1 truncate text-label text-foreground select-all">{userId}</code>
          <CopyButton value={userId} label="Copy" />
        </div>
      )}
      {/* One action: a plain link to /sign-in would keep the denied session, and Clerk sends a signed-in
          visitor straight back here. */}
      {!authBypass && (
        <SignOutButton redirectUrl="/sign-in">
          <Button variant="primary">Sign out and use another account</Button>
        </SignOutButton>
      )}
    </AuthFrame>
  );
}
