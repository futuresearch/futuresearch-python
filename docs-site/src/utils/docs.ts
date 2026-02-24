import fs from "fs";
import path from "path";
import matter from "gray-matter";
import { getAllNotebooks } from "./notebooks";

// Path to the docs content directory (relative to project root)
const DOCS_DIR = path.join(process.cwd(), "..", "docs");

export interface DocMeta {
  slug: string;
  title: string;
  metadataTitle?: string;
  description?: string;
  category: string;
  format: "md" | "mdx";
}

export interface Doc extends DocMeta {
  content: string;
}

function slugToTitle(slug: string): string {
  return slug
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/Llm/g, "LLM")
    .replace(/Ml/g, "ML")
    .replace(/Api/g, "API");
}

function getCategory(filePath: string): string {
  if (filePath.includes("reference/")) return "Reference";
  if (filePath.includes("case_studies/")) return "Case Studies";
  return "Guides";
}

export function getAllDocs(): DocMeta[] {
  const docs: DocMeta[] = [];

  function scanDir(dir: string, prefix: string = "") {
    const entries = fs.readdirSync(dir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);

      if (entry.isDirectory()) {
        // Skip directories served by other routes or not documentation
        if (["data", "case_studies", "claude-code-runs"].includes(entry.name)) continue;
        scanDir(fullPath, path.join(prefix, entry.name));
      } else if (entry.name.endsWith(".md") || entry.name.endsWith(".mdx")) {
        const isMdx = entry.name.endsWith(".mdx");
        const relativePath = path.join(prefix, entry.name);
        const slug = relativePath.replace(/\.mdx?$/, "");
        const content = fs.readFileSync(fullPath, "utf-8");
        const { data } = matter(content);

        docs.push({
          slug,
          title: data.title || slugToTitle(path.basename(slug)),
          metadataTitle: data.metadataTitle,
          description: data.description,
          category: getCategory(relativePath),
          format: isMdx ? "mdx" : "md",
        });
      }
    }
  }

  scanDir(DOCS_DIR);
  return docs;
}

export function getDocBySlug(slug: string): Doc | null {
  // Try .mdx first, then .md
  const baseSlug = slug.replace(/\.mdx?$/, "");

  for (const ext of [".mdx", ".md"] as const) {
    const fullPath = path.join(DOCS_DIR, `${baseSlug}${ext}`);

    if (fs.existsSync(fullPath)) {
      const fileContent = fs.readFileSync(fullPath, "utf-8");
      const { data, content } = matter(fileContent);

      return {
        slug: baseSlug,
        title: data.title || slugToTitle(path.basename(baseSlug)),
        metadataTitle: data.metadataTitle,
        description: data.description,
        category: getCategory(baseSlug),
        format: ext === ".mdx" ? "mdx" : "md",
        content,
      };
    }
  }

  return null;
}

// Slugs that are rendered inline on the homepage, not as standalone pages
const HOMEPAGE_ONLY_SLUGS = new Set(["installation"]);

export function getDocSlugs(): string[] {
  return getAllDocs()
    .filter((doc) => !HOMEPAGE_ONLY_SLUGS.has(doc.slug))
    .map((doc) => doc.slug);
}

// Navigation structure
export interface NavSection {
  title: string;
  href?: string;
  items: { slug: string; title: string; href?: string }[];
}

export function getNavigation(): NavSection[] {
  const docs = getAllDocs();
  const notebooks = getAllNotebooks();

  const guides = docs.filter((d) => d.category === "Guides");
  const reference = docs.filter((d) => d.category === "Reference");

  return [
    {
      title: "Overview",
      items: [
        { slug: "installation", title: "Installation", href: "/" },
        { slug: "getting-started", title: "Getting Started" },
        { slug: "api-key", title: "API Key", href: "https://everyrow.io/api-key" },
        { slug: "mcp-server", title: "MCP Server" },
        { slug: "skills-vs-mcp", title: "Skills vs MCP" },
        { slug: "progress-monitoring", title: "Progress Monitoring" },
        { slug: "chaining-operations", title: "Chaining Operations" },
        { slug: "github", title: "GitHub", href: "https://github.com/futuresearch/everyrow-sdk" },
      ],
    },
    {
      title: "API Reference",
      href: "/api",
      items: reference.map((d) => ({
        slug: d.slug,
        title: d.title.replace(/^reference\//, ""),
      })),
    },
    {
      title: "Guides",
      href: "/guides",
      items: guides
        .filter((d) => ![
          "getting-started",
          "chaining-operations",
          "installation",
          "progress-monitoring",
          "mcp-server",
          "skills-vs-mcp",
          "guides",
          "notebooks",
          "api",
          "case-studies",
        ].includes(d.slug))
        .map((d) => ({ slug: d.slug, title: d.title })),
    },
    {
      title: "Case Studies",
      href: "/case-studies",
      items: notebooks.map((n) => ({
        slug: `case-studies/${n.slug}`,
        title: n.title,
      })),
    },
  ];
}
