import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { auth } from "@clerk/nextjs/server";

import { AppShell, SIDEBAR_COOKIE } from "@/components/shell/app-shell";
import { authBypass, isPlatformAdmin } from "@/lib/auth";

// Every route in this group requires a signed-in user on the allowlist (DEC-020). src/proxy.ts runs the
// same check on every request, including client-side navigations.
export default async function AppLayout({ children }: LayoutProps<"/">) {
  if (!authBypass) {
    const { userId, redirectToSignIn } = await auth();
    if (!userId) return redirectToSignIn();
    if (!isPlatformAdmin(userId)) redirect("/not-authorized");
  }
  const collapsed = (await cookies()).get(SIDEBAR_COOKIE)?.value === "collapsed";
  return <AppShell defaultCollapsed={collapsed}>{children}</AppShell>;
}
