import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

import { authBypass, isPlatformAdmin } from "@/lib/auth";

// Auth gate (DEC-020): signed out → /sign-in; signed in but not on PLATFORM_ADMIN_USER_IDS →
// /not-authorized. The (app) layout runs the same check per Clerk's resource-based guidance; this copy also
// covers client-side navigations, which don't re-run the layout. Fails closed: without Clerk keys
// clerkMiddleware throws, and an empty allowlist admits nobody. /api/* is not matched: it is rewritten to
// the FastAPI service, which verifies the Clerk JWT itself.
const PUBLIC_PATHS = ["/sign-in", "/not-authorized"];
const isPublic = (path: string) => PUBLIC_PATHS.some((base) => path === base || path.startsWith(`${base}/`));

const clerkGate = clerkMiddleware(async (auth, req) => {
  if (isPublic(req.nextUrl.pathname)) return;
  const { userId, redirectToSignIn } = await auth();
  if (!userId) return redirectToSignIn();
  if (!isPlatformAdmin(userId)) return NextResponse.redirect(new URL("/not-authorized", req.url));
});

// `authBypass` is the constant `false` in production builds (see src/lib/auth.ts).
export default authBypass ? () => NextResponse.next() : clerkGate;

export const config = {
  matcher: ["/((?!api/|_next/|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)"],
};
