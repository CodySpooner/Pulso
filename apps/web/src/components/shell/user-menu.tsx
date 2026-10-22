"use client";

import { UserButton } from "@clerk/nextjs";

import { authBypass } from "@/lib/auth";

export function UserMenu() {
  if (authBypass) {
    return (
      <span
        role="img"
        aria-label="E2E test user (auth bypassed in development)"
        className="grid size-8 place-items-center rounded-full border border-border bg-secondary text-micro font-medium text-muted-foreground"
      >
        E2E
      </span>
    );
  }
  return <UserButton appearance={{ elements: { avatarBox: "size-8" } }} />;
}
