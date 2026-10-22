import { clerkSetup } from "@clerk/testing/playwright";

// Fetches a Clerk testing token with CLERK_SECRET_KEY (dev instances only) so the tests get past Clerk's
// bot protection. The token reaches the test workers through process.env.
export default async function globalSetup() {
  await clerkSetup();
}
