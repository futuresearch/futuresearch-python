import { notFound } from "next/navigation";
import { DocsLayout } from "@/components/DocsLayout";
import { getDocBySlug, getDocSlugs, getNavigation } from "@/utils/docs";
import { markdownToHtml } from "@/utils/markdown";
import { MDXContent } from "@/components/MDXContent";

interface PageProps {
  params: Promise<{ slug: string[] }>;
}

export async function generateStaticParams() {
  const slugs = getDocSlugs();
  return slugs.map((slug) => ({
    slug: slug.split("/"),
  }));
}

export async function generateMetadata({ params }: PageProps) {
  const { slug } = await params;
  const slugPath = slug.join("/");
  const doc = getDocBySlug(slugPath);

  if (!doc) {
    return { title: "Not Found" };
  }

  const canonicalUrl = `https://everyrow.io/docs/${slugPath}`;

  const pageTitle = doc.metadataTitle || doc.title;

  return {
    title: pageTitle,
    description: doc.description,
    alternates: {
      canonical: canonicalUrl,
    },
    openGraph: {
      title: pageTitle,
      description: doc.description,
      url: canonicalUrl,
      images: [{ url: "https://everyrow.io/everyrow-og.png" }],
    },
  };
}

export default async function DocPage({ params }: PageProps) {
  const { slug } = await params;
  const slugPath = slug.join("/");
  const doc = getDocBySlug(slugPath);

  if (!doc) {
    notFound();
  }

  const navigation = getNavigation();

  if (doc.format === "mdx") {
    return (
      <DocsLayout navigation={navigation}>
        <MDXContent source={doc.content} />
      </DocsLayout>
    );
  }

  const htmlContent = await markdownToHtml(doc.content);

  return (
    <DocsLayout navigation={navigation}>
      <article className="prose" dangerouslySetInnerHTML={{ __html: htmlContent }} />
    </DocsLayout>
  );
}
