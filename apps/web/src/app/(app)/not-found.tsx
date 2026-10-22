import Link from "next/link";
import { Compass } from "lucide-react";

import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";

export default function NotFound() {
  return (
    <div className="mx-auto w-full max-w-280 rounded-xl border border-border bg-card shadow-card">
      <EmptyState
        icon={Compass}
        headingLevel="h1"
        title="Page not found"
        action={
          <Button asChild variant="secondary">
            <Link href="/">Go to Daily Pulse</Link>
          </Button>
        }
      >
        This address isn&apos;t a Pulso page. Press <Kbd>Ctrl K</Kbd> to jump to any page.
      </EmptyState>
    </div>
  );
}
