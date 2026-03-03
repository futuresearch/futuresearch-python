import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "REST API Reference — everyrow",
  description:
    "Complete REST API reference for the everyrow API. All endpoints, request/response schemas, and authentication.",
  alternates: {
    canonical: "https://everyrow.io/docs/rest-api",
  },
  openGraph: {
    title: "REST API Reference — everyrow",
    description:
      "Complete REST API reference for the everyrow API. All endpoints, request/response schemas, and authentication.",
    url: "https://everyrow.io/docs/rest-api",
    images: [{ url: "https://everyrow.io/everyrow-og.png" }],
  },
};

export default function RestApiLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
