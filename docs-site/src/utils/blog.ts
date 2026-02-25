import fs from "fs";
import path from "path";
import matter from "gray-matter";

const BLOG_DIR = path.join(process.cwd(), "src", "blog");

export interface BlogPostMeta {
  slug: string;
  title: string;
  subtitle: string;
  description: string;
  date: Date;
  authors: string[];
  tags: string[];
  heroImage?: string;
}

export interface BlogPost extends BlogPostMeta {
  content: string;
}

function extractMeta(data: Record<string, unknown>, slug: string): Omit<BlogPostMeta, "slug"> {
  return {
    title: (data.title as string) || slug,
    subtitle: (data.subtitle as string) || "",
    description: (data.description as string) || "",
    date: data.date instanceof Date ? data.date : new Date(data.date as string),
    authors: (data.authors as string[]) || [],
    tags: (data.tags as string[]) || [],
    heroImage: (data.heroImage as string) || undefined,
  };
}

export function getAllBlogPosts(): BlogPostMeta[] {
  if (!fs.existsSync(BLOG_DIR)) {
    return [];
  }

  const files = fs.readdirSync(BLOG_DIR);
  const posts: BlogPostMeta[] = [];

  for (const file of files) {
    if (!file.endsWith(".mdx") && !file.endsWith(".md")) continue;

    const fullPath = path.join(BLOG_DIR, file);
    const fileContent = fs.readFileSync(fullPath, "utf-8");
    const { data } = matter(fileContent);
    const slug = file.replace(/\.mdx?$/, "");

    posts.push({ slug, ...extractMeta(data, slug) });
  }

  // Sort by date, newest first
  return posts.sort((a, b) => b.date.getTime() - a.date.getTime());
}

export function getBlogPostBySlug(slug: string): BlogPost | null {
  for (const ext of [".mdx", ".md"]) {
    const fullPath = path.join(BLOG_DIR, `${slug}${ext}`);

    if (fs.existsSync(fullPath)) {
      const fileContent = fs.readFileSync(fullPath, "utf-8");
      const { data, content } = matter(fileContent);

      return { slug, ...extractMeta(data, slug), content };
    }
  }

  return null;
}

export function formatDate(date: Date): string {
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function getBlogPostSlugs(): string[] {
  return getAllBlogPosts().map((p) => p.slug);
}
