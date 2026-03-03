import type { Metadata } from "next";
import Link from "next/link";
import { DocsLayout } from "@/components/DocsLayout";
import { getNavigation, getDocBySlug, type NavSection } from "@/utils/docs";
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

const SECTION_ICONS: Record<string, string> = {
  "Get Started": "rocket",
  Guides: "book",
  "API Reference": "code",
  "Case Studies": "lightbulb",
};

const SECTION_DESCRIPTIONS: Record<string, string> = {
  "Get Started": "Set up EveryRow in Claude.ai, Claude Code, and more",
  Guides: "Step-by-step tutorials for web research at scale",
  "API Reference": "API reference for all everyrow operations",
  "Case Studies": "Real-world examples with verified results",
};

const SECTION_LINKS: Record<string, string> = {
  "Get Started": "/claude-ai",
  "API Reference": "/api",
  Guides: "/guides",
  "Case Studies": "/case-studies",
};

function SectionCard({ section }: { section: NavSection }) {
  const icon = SECTION_ICONS[section.title] || "file";
  const description = SECTION_DESCRIPTIONS[section.title] || "";
  const firstItem = section.items[0];

  if (!firstItem) return null;

  const href = SECTION_LINKS[section.title] || `/${firstItem.slug}`;

  return (
    <Link href={href} className="landing-card">
      <div className="landing-card-icon" data-icon={icon}>
        {icon === "rocket" && (
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z" />
            <path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z" />
            <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0" />
            <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" />
          </svg>
        )}
        {icon === "book" && (
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
          </svg>
        )}
        {icon === "code" && (
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <polyline points="16 18 22 12 16 6" />
            <polyline points="8 6 2 12 8 18" />
          </svg>
        )}
        {icon === "lightbulb" && (
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5" />
            <path d="M9 18h6" />
            <path d="M10 22h4" />
          </svg>
        )}
      </div>
      <h2 className="landing-card-title">{section.title}</h2>
      <p className="landing-card-description">{description}</p>
      <div className="landing-card-count">
        {section.items.length} {section.items.length === 1 ? "page" : "pages"}
      </div>
    </Link>
  );
}

export default async function DocsHome() {
  const navigation = getNavigation();
  const installationDoc = getDocBySlug("installation");

  return (
    <DocsLayout navigation={navigation}>
      <div className="landing-hero">
        <h1 className="landing-title"><span className="landing-title-brand">everyrow</span> documentation</h1>
        <p className="landing-subtitle">
          A researcher for every row
        </p>
      </div>

      <div className="landing-grid">
        {navigation
          .filter((section) => section.title !== "Overview")
          .map((section) => (
            <SectionCard key={section.title} section={section} />
          ))}
      </div>

      {installationDoc && (
        <MDXContent source={installationDoc.content} />
      )}

      <div className="landing-quickstart">
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
