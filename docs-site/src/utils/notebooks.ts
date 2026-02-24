import fs from "fs";
import path from "path";
import matter from "gray-matter";

const NOTEBOOKS_DIR = path.join(process.cwd(), "src", "notebooks");
const SOURCE_NOTEBOOKS_DIR = path.join(process.cwd(), "..", "docs", "case_studies");

export interface NotebookMeta {
  slug: string;
  title: string;
  description: string;
}

export interface Notebook extends NotebookMeta {
  html: string;
}

interface NotebookCell {
  cell_type: string;
  source: string | string[];
}

interface NotebookJson {
  cells: NotebookCell[];
  metadata?: {
    everyrow?: {
      description?: string;
    };
  };
}

function extractMetadataFromSource(slug: string): { title: string; description: string } {
  const sourcePath = path.join(SOURCE_NOTEBOOKS_DIR, slug, "notebook.ipynb");

  if (!fs.existsSync(sourcePath)) {
    return { title: slugToTitle(slug), description: "" };
  }

  try {
    const content = fs.readFileSync(sourcePath, "utf-8");
    const notebook: NotebookJson = JSON.parse(content);
    const cells = notebook.cells || [];

    // Extract title from first markdown cell's H1
    let title = slugToTitle(slug);
    if (cells.length > 0 && cells[0].cell_type === "markdown") {
      const source = cells[0].source;
      const cellContent = Array.isArray(source) ? source.join("") : source;
      const firstLine = cellContent.trim().split("\n")[0];
      if (firstLine.startsWith("# ")) {
        title = firstLine.slice(2).trim();
      }
    }

    // Extract description from notebook metadata
    const description = notebook.metadata?.everyrow?.description || "";

    return { title, description };
  } catch {
    return { title: slugToTitle(slug), description: "" };
  }
}

function slugToTitle(slug: string): string {
  return slug
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/Crm/g, "CRM")
    .replace(/Llm/g, "LLM")
    .replace(/Ml/g, "ML")
    .replace(/Api/g, "API");
}

export function getAllNotebooks(): NotebookMeta[] {
  const slugSet = new Set<string>();
  const results: NotebookMeta[] = [];

  // Discover from HTML notebook files
  if (fs.existsSync(NOTEBOOKS_DIR)) {
    const files = fs.readdirSync(NOTEBOOKS_DIR);
    for (const f of files) {
      if (!f.endsWith(".html")) continue;
      const slug = f.replace(/\.html$/, "");
      slugSet.add(slug);
    }
  }

  // Discover from case study directories with content.mdx
  if (fs.existsSync(SOURCE_NOTEBOOKS_DIR)) {
    const dirs = fs.readdirSync(SOURCE_NOTEBOOKS_DIR, { withFileTypes: true });
    for (const dir of dirs) {
      if (!dir.isDirectory()) continue;
      const mdxPath = path.join(SOURCE_NOTEBOOKS_DIR, dir.name, "content.mdx");
      if (fs.existsSync(mdxPath)) {
        slugSet.add(dir.name);
      }
    }
  }

  for (const slug of slugSet) {
    // Prefer MDX frontmatter for title/description
    const mdx = getCaseStudyMdx(slug);
    if (mdx) {
      results.push({ slug, title: mdx.title, description: mdx.description });
    } else {
      const { title, description } = extractMetadataFromSource(slug);
      results.push({ slug, title, description });
    }
  }

  return results.sort((a, b) => a.title.localeCompare(b.title));
}

export function getNotebookBySlug(slug: string): Notebook | null {
  const filePath = path.join(NOTEBOOKS_DIR, `${slug}.html`);

  if (!fs.existsSync(filePath)) {
    return null;
  }

  const html = fs.readFileSync(filePath, "utf-8");
  const { title, description } = extractMetadataFromSource(slug);

  return {
    slug,
    title,
    description,
    html,
  };
}

export function getNotebookSlugs(): string[] {
  return getAllNotebooks().map((n) => n.slug);
}

export interface CaseStudyMdx {
  title: string;
  metadataTitle?: string;
  description: string;
  content: string;
}

export function getCaseStudyMdx(slug: string): CaseStudyMdx | null {
  const mdxPath = path.join(SOURCE_NOTEBOOKS_DIR, slug, "content.mdx");

  if (!fs.existsSync(mdxPath)) {
    return null;
  }

  const fileContent = fs.readFileSync(mdxPath, "utf-8");
  const { data, content } = matter(fileContent);

  return {
    title: data.title || slugToTitle(slug),
    metadataTitle: data.metadataTitle,
    description: data.description || "",
    content,
  };
}
