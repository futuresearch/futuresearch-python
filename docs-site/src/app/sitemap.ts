import { MetadataRoute } from "next";
import { getDocSlugs } from "@/utils/docs";
import { getNotebookSlugs } from "@/utils/notebooks";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = "https://everyrow.io/docs";

  const docSlugs = getDocSlugs();
  const notebookSlugs = getNotebookSlugs();

  const hubSlugs = new Set(["guides", "case-studies", "api"]);

  const docPages = docSlugs.map((slug) => ({
    url: `${baseUrl}/${slug}`,
    lastModified: new Date(),
    changeFrequency: "weekly" as const,
    priority: hubSlugs.has(slug) ? 0.9 : 0.8,
  }));

  const notebookPages = notebookSlugs.map((slug) => ({
    url: `${baseUrl}/case-studies/${slug}`,
    lastModified: new Date(),
    changeFrequency: "monthly" as const,
    priority: 0.7,
  }));

  return [
    {
      url: baseUrl,
      lastModified: new Date(),
      changeFrequency: "weekly" as const,
      priority: 1,
    },
    ...docPages,
    ...notebookPages,
  ];
}
