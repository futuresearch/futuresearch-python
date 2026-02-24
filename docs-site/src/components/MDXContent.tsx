import { MDXRemote } from "next-mdx-remote/rsc";
import { InstallationTabs, TabContent } from "./InstallationTabs";
import { ChainedOpsTabs, StepContent } from "./ChainedOpsTabs";
import { GuideTabs, GuideTabContent } from "./GuideTabs";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";

const components = {
  InstallationTabs,
  TabContent,
  ChainedOpsTabs,
  StepContent,
  GuideTabs,
  GuideTabContent,
};

interface MDXContentProps {
  source: string;
}

export async function MDXContent({ source }: MDXContentProps) {
  return (
    <article className="prose">
      <MDXRemote
        source={source}
        components={components}
        options={{
          mdxOptions: {
            remarkPlugins: [remarkGfm],
            rehypePlugins: [rehypeHighlight],
          },
        }}
      />
    </article>
  );
}
