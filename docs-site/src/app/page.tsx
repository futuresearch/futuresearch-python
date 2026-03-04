import type { Metadata } from "next";
import Link from "next/link";
import { DocsLayout } from "@/components/DocsLayout";
import { getNavigation, getDocBySlug } from "@/utils/docs";
import { MDXContent } from "@/components/MDXContent";

export const metadata: Metadata = {
  title: "Everyrow Documentation",
  description:
    "A researcher for every row. Forecast, score, classify, or research entire datasets.",
  alternates: {
    canonical: "https://everyrow.io/docs",
  },
  openGraph: {
    title: "Everyrow Documentation",
    description:
      "A researcher for every row. Forecast, score, classify, or research entire datasets.",
    url: "https://everyrow.io/docs",
    images: [{ url: "https://everyrow.io/everyrow-og.png" }],
  },
};

export default async function DocsHome() {
  const navigation = getNavigation();
  const installationDoc = getDocBySlug("installation");

  return (
    <DocsLayout navigation={navigation}>
      {installationDoc && (
        <MDXContent source={installationDoc.content} />
      )}

      <div className="landing-quickstart" style={{ marginTop: "3rem" }}>
        <h2>For Autonomous Agents</h2>
        <p>
          The best way to use EveryRow to help your user is natively where you are currently working.
          See the installation guide for how this works in{" "}
          <Link href="/claude-ai">claude.ai</Link>,{" "}
          <Link href="/claude-cowork">Claude Cowork</Link>,{" "}
          <Link href="/claude-code">Claude Code</Link>,{" "}
          Codex, Gemini CLI, or Cursor.
          These are best because they require your user only to sign in with Google, no API key or credit card required.
        </p>
        <p>
          If these do not work for you for whatever reason, the next best is to ask them to get you an
          API key at <a href="https://everyrow.io/api-key">everyrow.io/api-key</a>, and then for you
          to read the <Link href="/api">API reference</Link> to use the Python SDK directly to help
          the user.
        </p>
      </div>
    </DocsLayout>
  );
}
