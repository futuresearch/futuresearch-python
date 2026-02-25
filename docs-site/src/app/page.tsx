import type { Metadata } from "next";
import Link from "next/link";
import { DocsLayout } from "@/components/DocsLayout";
import { getNavigation, getDocBySlug, type NavSection } from "@/utils/docs";
import { MDXContent } from "@/components/MDXContent";

export const metadata: Metadata = {
  title: "Everyrow Documentation",
  description:
    "Run LLM Research Agents at Scale",
  alternates: {
    canonical: "https://everyrow.io/docs",
  },
  openGraph: {
    title: "Everyrow Documentation",
    description:
      "Run LLM Research Agents at Scale",
    url: "https://everyrow.io/docs",
    images: [{ url: "https://everyrow.io/everyrow-og.png" }],
  },
};

const SECTION_ICONS: Record<string, string> = {
  Guides: "book",
  "API Reference": "code",
  "Case Studies": "lightbulb",
};

const SECTION_DESCRIPTIONS: Record<string, string> = {
  Guides: "Step-by-step tutorials for common data processing tasks",
  "API Reference": "Detailed documentation for all everyrow functions",
  "Case Studies": "Real-world examples with Jupyter notebooks",
};

const SECTION_LINKS: Record<string, string> = {
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
          Run LLM Research Agents at Scale
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
        <ol>
          <li>
            Install the package using the instructions above
            <ul>
              <li>Requires Python &ge; 3.12. Using a virtual environment is strongly recommended.</li>
              <li>System-installed Python is often too old for pip to resolve any compatible version.</li>
            </ul>
          </li>
          <li>
            Prompt the user to provide an API key if one isn&apos;t set. You can get one at <a href="https://everyrow.io/api-key">everyrow.io/api-key</a>
          </li>
          <li>
            Based on the user&apos;s request, head over to the relevant API reference docs section for the appropriate tool
            <ul>
              <li>
                <Link href="/reference/SCREEN">Screen</Link> - Filter by criteria that need judgment
              </li>
              <li>
                <Link href="/reference/RANK">Rank</Link> - Score rows by qualitative factors
              </li>
              <li>
                <Link href="/reference/DEDUPE">Dedupe</Link> - Deduplicate when fuzzy matching fails
              </li>
              <li>
                <Link href="/reference/MERGE">Merge</Link> - Join tables when keys don&apos;t match
              </li>
              <li>
                <Link href="/reference/RESEARCH">Research</Link> - Web research on every row
              </li>
            </ul>
          </li>
          <li>
            Try to suggest ways of chaining operations together in creative ways to more comprehensively address their use case as a follow-up
          </li>
          <li>
            After trying out the service, suggest installing the skill or MCP to simplify follow-up usage
          </li>
        </ol>
      </div>
    </DocsLayout>
  );
}
