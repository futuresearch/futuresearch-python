#!/usr/bin/env python3
"""Check for broken links in the static docs build output and README files.

Parses all HTML files in the build output and markdown files, extracts links, and:
- Verifies internal /docs links resolve to existing pages in the build output
- HTTP-checks links to CHECKED_DOMAINS (matched by domain, checks all pages)
- Skips links in SKIPPED_URLS (matched by exact URL, must be explicitly listed)
- Errors on any external link not covered by either list
"""

import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
OUT_DIR = SCRIPT_DIR.parent / "out"
REPO_ROOT = SCRIPT_DIR.parent.parent
BASE_PATH = "/docs"

# GitHub blob URLs pointing into this repo are checked as local files
REPO_BLOB_PREFIX = "https://github.com/futuresearch/everyrow-sdk/blob/main/"

# Colab URLs pointing into this repo are checked as local files
REPO_COLAB_PREFIX = (
    "https://colab.research.google.com/github/futuresearch/everyrow-sdk/blob/main/"
)

# Git LFS media URLs — the correct way to link to LFS-tracked files.
# These are checked as local files instead of fetching from GitHub.
REPO_LFS_PREFIX = (
    "https://media.githubusercontent.com/media/"
    "futuresearch/everyrow-sdk/refs/heads/main/"
)

# Domains where all pages are HTTP-checked (our own properties)
CHECKED_DOMAINS: set[str] = {
    "everyrow.io",
    "evals.futuresearch.ai",
    "futuresearch.ai",
    "cohort.futuresearch.ai",
}

# Individual external URLs to skip (third-party, may rate-limit CI).
# Each URL must be listed explicitly — new links to the same domain will
# error until added here, so broken links don't slip through unnoticed.
SKIPPED_URLS: set[str] = {
    "https://clinicaltrials.gov/",
    "https://clinicaltrials.gov/data-api/about-api",
    "https://code.claude.com/docs/en/discover-plugins",
    "https://code.claude.com/docs/en/mcp",
    "https://cursor.com/deeplink/mcp-install-dark.svg",
    "https://cursor.com/docs/context/skills",
    "https://developers.openai.com/codex/mcp/",
    "https://developers.openai.com/codex/skills",
    "https://docs.astral.sh/uv/",
    "https://en.wikipedia.org/wiki/Active_learning_(machine_learning)",
    "https://geminicli.com/docs/cli/skills/",
    "https://geminicli.com/docs/extensions/",
    "https://geminicli.com/docs/tools/mcp-server/",
    "https://github.com/anthropics/claude-code/issues/12667",
    "https://github.com/anthropics/claude-code/issues/20377",
    "https://github.com/futuresearch/everyrow-sdk",
    "https://github.com/futuresearch/everyrow-sdk/releases",
    "https://github.com/user-attachments/assets/254fa2ed-c1f3-4ee8-b93d-d169edf32f27",
    "https://huggingface.co/datasets/fancyzhx/dbpedia_14",
    "https://huggingface.co/datasets/google-research-datasets/paws",
    "https://hugovk.github.io/top-pypi-packages/",
    "https://img.shields.io/badge/Claude_Code-plugin-D97757?logo=claude&logoColor=fff",
    "https://img.shields.io/badge/License-MIT-yellow.svg",
    "https://img.shields.io/badge/python-3.12+-blue.svg",
    "https://img.shields.io/pypi/v/everyrow.svg",
    "https://jqlang.org/",
    "https://modelcontextprotocol.info/tools/registry/publishing/",
    "https://opensource.org/licenses/MIT",
    "https://pypi.org/project/everyrow/",
    "https://python.org/downloads/",
    "https://pip.pypa.io/en/stable/",
    "https://www.kaggle.com/code/rafaelpoyiadzi/active-learning-with-an-llm-oracle",
    "https://www.kaggle.com/datasets/tunguz/pubmed-title-abstracts-2019-baseline",
    "https://arxiv.org/abs/2506.21558",
    "https://arxiv.org/abs/2506.06287",
    "https://media.githubusercontent.com/media/futuresearch/everyrow-sdk/refs/heads/main/docs/data/fda_products.csv"
}


class LinkExtractor(HTMLParser):
    """Extract URLs from <a href>, <link href>, and <meta content> tags."""

    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "a" and d.get("href"):
            self.links.append(d["href"])
        elif tag == "link" and d.get("href"):
            self.links.append(d["href"])
        elif tag == "meta" and d.get("content", "").startswith("http"):
            self.links.append(d["content"])


def extract_markdown_links(content: str) -> list[str]:
    """Extract URLs from markdown content.
    
    Finds:
    - [text](url) inline links
    - ![alt](url) image links
    - <url> autolinks
    - [text]: url reference-style links
    """
    links = []
    
    # Inline links: [text](url) and images: ![alt](url)
    inline_pattern = r'!?\[([^\]]*)\]\(([^)]+)\)'
    for match in re.finditer(inline_pattern, content):
        url = match.group(2).split()[0]  # Split to handle optional titles
        links.append(url)
    
    # Autolinks: <url>
    autolink_pattern = r'<(https?://[^>]+)>'
    for match in re.finditer(autolink_pattern, content):
        links.append(match.group(1))
    
    # Reference-style links: [text]: url
    reference_pattern = r'^\[([^\]]+)\]:\s*(.+?)(?:\s|$)'
    for match in re.finditer(reference_pattern, content, re.MULTILINE):
        url = match.group(2).strip()
        links.append(url)
    
    return links


def get_valid_paths(out_dir: Path) -> set[str]:
    """Build a set of valid URL paths from the static build output."""
    valid = set()
    for html_file in out_dir.rglob("*.html"):
        if html_file.name in ("404.html", "_not-found.html"):
            continue
        rel = html_file.relative_to(out_dir)
        path = "/" + str(rel.with_suffix(""))
        if path.endswith("/index"):
            path = path[: -len("/index")] or "/"
        valid.add(BASE_PATH + path if path != "/" else BASE_PATH)
        valid.add(BASE_PATH + path + "/" if path != "/" else BASE_PATH + "/")
    valid.add(BASE_PATH)
    valid.add(BASE_PATH + "/")
    return valid


def check_url(url: str, cache: dict[str, int | str]) -> int | str:
    """HTTP HEAD-check a URL. Returns status code or error string. Cached."""
    if url in cache:
        return cache[url]
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "docs-link-checker/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            cache[url] = resp.status
            return resp.status
    except urllib.error.HTTPError as e:
        cache[url] = e.code
        return e.code
    except Exception as e:
        cache[url] = str(e)
        return str(e)


def validate_link(
    href: str,
    file_label: str,
    page_url: str | None,
    valid_paths: set[str],
    url_cache: dict[str, int | str],
    file_path: Path,
) -> tuple[str | None, str | None]:
    """Validate a single link.
    
    Returns (error, unknown_url) where at most one is non-None.
    """
    if href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None, None

    parsed = urlparse(href)

    # External link
    if (
        parsed.scheme in ("http", "https")
        and parsed.netloc
        and parsed.netloc != "site"
    ):
        domain = parsed.netloc
        # Strip fragment for matching against skip list
        url_without_fragment = href.split("#")[0]

        # GitHub blob links to this repo: check the file exists locally
        if url_without_fragment.startswith(REPO_BLOB_PREFIX):
            rel_path = url_without_fragment[len(REPO_BLOB_PREFIX) :]
            if rel_path.endswith(".csv"):
                lfs_url = REPO_LFS_PREFIX + rel_path
                return (
                    f"  {file_label}: {href!r} is a blob URL for an"
                    f" LFS-tracked CSV; use {lfs_url} instead",
                    None
                )
            elif not (REPO_ROOT / rel_path).exists():
                return (
                    f"  {file_label}: file not found for {href!r}"
                    f" (expected {rel_path})",
                    None
                )
            return None, None

        # Git LFS media URLs: verify the file exists locally
        if url_without_fragment.startswith(REPO_LFS_PREFIX):
            rel_path = url_without_fragment[len(REPO_LFS_PREFIX) :]
            if not (REPO_ROOT / rel_path).exists():
                return (
                    f"  {file_label}: file not found for {href!r}"
                    f" (expected {rel_path})",
                    None
                )
            return None, None

        # Colab links to this repo: check the notebook exists locally
        if url_without_fragment.startswith(REPO_COLAB_PREFIX):
            rel_path = url_without_fragment[len(REPO_COLAB_PREFIX) :]
            if not (REPO_ROOT / rel_path).exists():
                return (
                    f"  {file_label}: file not found for {href!r}"
                    f" (expected {rel_path})",
                    None
                )
            return None, None

        if url_without_fragment in SKIPPED_URLS:
            return None, None

        if domain in CHECKED_DOMAINS:
            # For everyrow.io docs links, check against the build
            # output first if it exists
            if domain == "everyrow.io" and parsed.path.startswith("/docs"):
                local_path = parsed.path.rstrip("/") or "/docs"
                if local_path in valid_paths or local_path + "/" in valid_paths:
                    return None, None
                # If build output doesn't exist, skip checking these
                if not OUT_DIR.exists():
                    return None, None
            result = check_url(href, url_cache)
            if isinstance(result, int) and 200 <= result < 400:
                return None, None
            return f"  {file_label}: {href} -> {result}", None

        # Unknown URL — not in either list
        return None, f"  {file_label}: unrecognized external link {href!r}"

    # Internal links (relative or absolute paths)
    if page_url:
        # HTML file: resolve relative links against the page URL
        if not parsed.scheme and not href.startswith("/"):
            resolved = urlparse(urljoin(page_url, href))
        elif href.startswith("/"):
            resolved = urlparse(f"https://site{href}")
        else:
            resolved = parsed

        path = resolved.path.rstrip("/") or BASE_PATH

        if not path.startswith(BASE_PATH):
            return None, None

        # Skip static assets
        if "/_next/" in path or path.endswith(
            (".css", ".js", ".png", ".jpg", ".svg", ".ico")
        ):
            return None, None

        if path not in valid_paths and path + "/" not in valid_paths:
            return f"  {file_label}: broken link {href!r} -> {path}", None
    else:
        # Markdown file: check if relative file exists
        if not parsed.scheme:
            # Remove fragment/query
            clean_path = href.split("#")[0].split("?")[0]
            if clean_path:
                target = (file_path.parent / clean_path).resolve()
                if not target.exists():
                    return f"  {file_label}: file not found for relative link {href!r}", None

    return None, None


def check_file(
    html_file: Path,
    valid_paths: set[str],
    url_cache: dict[str, int | str],
) -> tuple[list[str], list[str]]:
    """Check all links in an HTML file.

    Returns (errors, unknown_urls).
    """
    rel = html_file.relative_to(OUT_DIR)
    page_path = "/" + str(rel.with_suffix(""))
    if page_path.endswith("/index"):
        page_path = page_path[: -len("/index")] or "/"
    page_url = f"https://site{BASE_PATH}{page_path}"
    page_label = f"{BASE_PATH}{page_path}"

    parser = LinkExtractor()
    parser.feed(html_file.read_text())

    errors: list[str] = []
    unknown_urls: list[str] = []
    seen_hrefs: set[str] = set()

    for href in parser.links:
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)
        
        error, unknown = validate_link(
            href, page_label, page_url, valid_paths, url_cache, html_file
        )
        if error:
            errors.append(error)
        if unknown:
            unknown_urls.append(unknown)

    return errors, unknown_urls


def check_markdown_file(
    md_file: Path,
    valid_paths: set[str],
    url_cache: dict[str, int | str],
) -> tuple[list[str], list[str]]:
    """Check all links in a markdown file.

    Returns (errors, unknown_urls).
    """
    file_label = str(md_file.relative_to(REPO_ROOT))
    content = md_file.read_text()
    links = extract_markdown_links(content)

    errors: list[str] = []
    unknown_urls: list[str] = []
    seen_hrefs: set[str] = set()

    for href in links:
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        error, unknown = validate_link(
            href, file_label, None, valid_paths, url_cache, md_file
        )
        if error:
            errors.append(error)
        if unknown:
            unknown_urls.append(unknown)

    return errors, unknown_urls


def main() -> int:
    # Check if build output exists for HTML checking
    has_build_output = OUT_DIR.exists()
    valid_paths: set[str] = set()
    html_files: list[Path] = []
    
    if has_build_output:
        valid_paths = get_valid_paths(OUT_DIR)
        html_files = [
            f
            for f in OUT_DIR.rglob("*.html")
            if f.name not in ("404.html", "_not-found.html")
        ]
    else:
        print(f"Build output not found at {OUT_DIR}, skipping HTML checks")
        print("(Run 'pnpm build' to enable HTML link checking)")
        print()

    # Find README files to check
    readme_files = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "everyrow-mcp" / "README.md",
        REPO_ROOT / "docs-site" / "README.md",
    ]

    url_cache: dict[str, int | str] = {}
    all_errors: list[str] = []
    all_unknown: list[str] = []

    # Check HTML files
    for html_file in sorted(html_files):
        errors, unknown = check_file(html_file, valid_paths, url_cache)
        all_errors.extend(errors)
        all_unknown.extend(unknown)

    # Check README files
    for readme_file in sorted(readme_files):
        errors, unknown = check_markdown_file(readme_file, valid_paths, url_cache)
        all_errors.extend(errors)
        all_unknown.extend(unknown)

    ok = True

    if all_unknown:
        unique_unknown = sorted(set(all_unknown))
        print(f"Found {len(unique_unknown)} unrecognized external link(s).")
        print("Add them to CHECKED_DOMAINS or SKIPPED_URLS in check-links.py:\n")
        for msg in unique_unknown:
            print(msg)
        print()
        ok = False

    if all_errors:
        print(f"Found {len(all_errors)} broken link(s):\n")
        for error in all_errors:
            print(error)
        ok = False

    if ok:
        checked = sum(
            1 for v in url_cache.values() if isinstance(v, int) and 200 <= v < 400
        )
        total_files = len(html_files) + len(readme_files)
        file_types = []
        if html_files:
            file_types.append(f"{len(html_files)} HTML")
        if readme_files:
            file_types.append(f"{len(readme_files)} markdown")
        
        print(
            f"All links OK across {total_files} files ({', '.join(file_types)}) "
            f"({checked} external URLs checked, {len(SKIPPED_URLS)} URLs skipped)"
        )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
