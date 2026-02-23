import { notFound } from "next/navigation";
import { DocsLayout } from "@/components/DocsLayout";
import { NotebookActions } from "@/components/NotebookActions";
import { getNavigation } from "@/utils/docs";
import { getNotebookBySlug, getNotebookSlugs } from "@/utils/notebooks";

interface PageProps {
  params: Promise<{ slug: string }>;
}

export async function generateStaticParams() {
  const slugs = getNotebookSlugs();
  return slugs.map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: PageProps) {
  const { slug } = await params;
  const notebook = getNotebookBySlug(slug);

  if (!notebook) {
    return { title: "Not Found" };
  }

  const canonicalUrl = `https://everyrow.io/docs/case-studies/${slug}`;
  const description = notebook.description || `Case study: ${notebook.title}`;

  return {
    title: notebook.title,
    description,
    alternates: {
      canonical: canonicalUrl,
    },
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
