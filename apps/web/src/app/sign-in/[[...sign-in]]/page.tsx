import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { SignIn } from "@clerk/nextjs";

import { AuthFrame } from "@/components/pulso/auth-frame";
import { authBypass } from "@/lib/auth";

export const metadata: Metadata = { title: "Sign in" };

export default function SignInPage() {
  if (authBypass) redirect("/");
  return (
    <AuthFrame title="Sign in to Pulso" description="The pulse of what's selling.">
      <SignIn routing="path" path="/sign-in" appearance={{ elements: { header: "hidden" } }} />
    </AuthFrame>
  );
}
