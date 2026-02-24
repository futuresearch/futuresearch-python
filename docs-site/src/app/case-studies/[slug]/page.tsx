import { notFound } from "next/navigation";
import { DocsLayout } from "@/components/DocsLayout";
import { NotebookActions } from "@/components/NotebookActions";
import { MDXContent } from "@/components/MDXContent";
import { getNavigation } from "@/utils/docs";
import {
  getCaseStudyMdx,
  getNotebookBySlug,
  getNotebookSlugs,
} from "@/utils/notebooks";

interface PageProps {
  params: Promise<{ slug: string }>;
}

export async function generateStaticParams() {
  const slugs = getNotebookSlugs();
  return slugs.map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: PageProps) {
  const { slug } = await params;

  const mdx = getCaseStudyMdx(slug);
  if (mdx) {
    const canonicalUrl = `https://everyrow.io/docs/case-studies/${slug}`;
    const pageTitle = mdx.metadataTitle || mdx.title;
    const pageDescription = mdx.description || `Case study: ${mdx.title}`;
    return {
      title: pageTitle,
      description: pageDescription,
      alternates: { canonical: canonicalUrl },
      openGraph: {
        title: pageTitle,
        description: pageDescription,
        url: canonicalUrl,
        images: [{ url: "https://everyrow.io/everyrow-og.png" }],
      },
    };
  }

  const notebook = getNotebookBySlug(slug);
  if (!notebook) {
    return { title: "Not Found" };
  }

  const canonicalUrl = `https://everyrow.io/docs/case-studies/${slug}`;
  const description = notebook.description || `Case study: ${notebook.title}`;

  return {
    title: notebook.title,
    description,
    alternates: { canonical: canonicalUrl },
    openGraph: {
      title: notebook.title,
      description,
      url: canonicalUrl,
      images: [{ url: "https://everyrow.io/everyrow-og.png" }],
    },
  };
}

export default async function NotebookPage({ params }: PageProps) {
  const { slug } = await params;

  const mdx = getCaseStudyMdx(slug);
  if (mdx) {
    const navigation = getNavigation();
    return (
      <DocsLayout navigation={navigation}>
        <MDXContent source={mdx.content} />
      </DocsLayout>
    );
  }

  const notebook = getNotebookBySlug(slug);
  if (!notebook) {
    notFound();
  }

  const navigation = getNavigation();

  return (
    <DocsLayout navigation={navigation}>
      <NotebookActions slug={slug} />
      <article
        className="notebook-content"
        dangerouslySetInnerHTML={{ __html: notebook.html }}
      />
    </DocsLayout>
  );
}
