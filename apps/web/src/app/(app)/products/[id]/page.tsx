import type { Metadata } from "next";

import { ProductPage } from "./product-page";

export const metadata: Metadata = { title: "Product" };

// UX-3: the product page shell. The data comes from GET /v1/products/{id} on the client, like Data Health.
export default async function Page({ params }: PageProps<"/products/[id]">) {
  return <ProductPage id={(await params).id} />;
}
