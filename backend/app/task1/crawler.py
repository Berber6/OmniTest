"""Document crawler using crawl4ai to crawl the 4gaboards documentation site."""

import asyncio
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from typing import Optional

import aiohttp
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.async_crawler_strategy import AsyncHTTPCrawlerStrategy

from .models import CrawledPage

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://docs.4gaboards.com"


async def crawl_docs(
    base_url: str = DEFAULT_BASE_URL,
    output_dir: str = "data/crawled_docs",
) -> list[CrawledPage]:
    """Crawl the documentation site and save pages as markdown.

    Uses sitemap.xml for page discovery when available, falling back
    to internal link extraction from the root page. Uses the HTTP-only
    crawler strategy (no browser required).

    Args:
        base_url: Root URL of the documentation site.
        output_dir: Directory to save crawled page data.

    Returns:
        List of CrawledPage objects with content and metadata.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Save and clear proxy env vars that interfere with HTTP crawling
    saved_proxy_vars = {}
    for key in list(os.environ.keys()):
        if "proxy" in key.lower():
            saved_proxy_vars[key] = os.environ[key]
            del os.environ[key]

    # Load existing pages for incremental crawl
    existing_pages = load_crawled_pages(output_dir)
    existing_urls = {page.url for page in existing_pages}
    logger.info(f"Found {len(existing_urls)} existing pages in manifest")

    pages: list[CrawledPage] = []

    try:
        # Step 1: Discover all URLs to crawl (sitemap or link extraction)
        urls_to_crawl = await _discover_urls(base_url)

        # Filter out URLs already in manifest
        new_urls = [url for url in urls_to_crawl if url not in existing_urls]
        logger.info(
            f"Discovered {len(urls_to_crawl)} URLs, {len(new_urls)} new "
            f"(skipping {len(existing_urls)} existing)"
        )

        if not new_urls:
            logger.info("No new URLs to crawl; returning existing pages")
            return existing_pages

        # Step 2: Crawl only new URLs using HTTP-only strategy
        http_strategy = AsyncHTTPCrawlerStrategy()
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            word_count_threshold=10,
            exclude_external_links=True,
            verbose=False,
        )

        try:
            async with AsyncWebCrawler(crawler_strategy=http_strategy) as crawler:
                for url in new_urls:
                    try:
                        result = await crawler.arun(
                            url=url,
                            config=run_config,
                        )

                        if result.success and result.markdown:
                            content = _extract_markdown_content(result.markdown)
                            content = _filter_markdown_content(content, url)
                            title = ""
                            if result.metadata:
                                title = result.metadata.get("title", "")

                            # Download images from this page
                            images_dir = os.path.join(output_dir, "images")
                            page_images = []
                            if hasattr(result, "media") and result.media:
                                page_images = await _download_images(
                                    result.media, base_url, images_dir,
                                )

                            page = CrawledPage(
                                url=url,
                                title=title,
                                content=content,
                                metadata={
                                    "depth": 0 if url == base_url or url == base_url + "/" else 1,
                                },
                                images=page_images,
                            )
                            pages.append(page)
                            logger.info(
                                f"Crawled: {url} ({len(page.content)} chars, "
                                f"{len(page_images)} images)"
                            )
                        else:
                            logger.warning(f"Failed to crawl {url}: no markdown content")
                    except Exception as exc:
                        logger.error(f"Error crawling {url}: {exc}")
                        continue

        except Exception as exc:
            logger.error(f"Crawl session failed: {exc}")

        if not pages:
            logger.warning("No new pages were successfully crawled")
            return existing_pages

        # Merge new pages with existing pages and save combined manifest
        all_pages = existing_pages + pages
        _save_pages(all_pages, output_dir)
        logger.info(
            f"Crawl complete: {len(pages)} new pages, {len(all_pages)} total "
            f"pages saved to {output_dir}"
        )

        return all_pages
    finally:
        # Restore proxy env vars so ChromaDB/LLM can reach HuggingFace
        for key, value in saved_proxy_vars.items():
            os.environ[key] = value


def _extract_markdown_content(markdown_result) -> str:
    """Extract raw markdown text from crawl4ai's result.

    In crawl4ai 0.8.x, the 'markdown' attribute returns a
    StringCompatibleMarkdown object (not a plain string). It acts like
    a string via __str__, and also has raw_markdown/fit_markdown
    attributes for structured access.
    """
    # Try structured access first (more reliable)
    if hasattr(markdown_result, 'raw_markdown') and markdown_result.raw_markdown:
        return str(markdown_result.raw_markdown)

    # Fall back to fit_markdown if available and non-empty
    if hasattr(markdown_result, 'fit_markdown') and markdown_result.fit_markdown:
        return str(markdown_result.fit_markdown)

    # Last resort: cast to string (works for StringCompatibleMarkdown)
    return str(markdown_result)


def _filter_markdown_content(content: str, url: str) -> str:
    """Remove navigation, sidebar, and footer boilerplate from crawled markdown.

    Targets patterns typical of Docusaurus-generated documentation sites.
    Operates conservatively: only removes lines that are clearly
    nav/sidebar/footer content. Ambiguous lines are kept.

    Docusaurus pages follow a consistent structure:
      1. Navbar: "Skip to main content", logo link, section nav links
      2. Language switcher: [English]/[Polski] links
      3. Sidebar TOC: indented link lists (  * [Topic](url))
      4. Breadcrumb: short nav trail before the heading
      5. "On this page" label
      6. Main content: starts with # Title heading
      7. Prev/Next navigation links at bottom
      8. Bottom TOC anchors:   * [Section](url#anchor)
      9. Footer: logo, Community/Docs links, copyright

    Args:
        content: Raw markdown text from crawl4ai.
        url: Source URL (used for context in logging only).

    Returns:
        Filtered markdown with nav/sidebar/footer removed.
    """
    lines = content.split("\n")

    # --- Phase 1: Find the main content start (first # heading) ---
    heading_idx = None
    for i, line in enumerate(lines):
        if line.startswith("# "):
            heading_idx = i
            break

    # --- Phase 2: Remove pre-heading boilerplate ---
    # All lines before the heading that match nav/sidebar patterns are removed.
    pre_heading_kept: list[str] = []
    if heading_idx is not None:
        for line in lines[:heading_idx]:
            if _is_nav_sidebar_line(line):
                continue
            stripped = line.strip()
            # "On this page" label is always boilerplate before the heading
            if stripped == "On this page":
                continue
            # Breadcrumb plain-text items: short standalone words like
            # "Card", "Structure Overview" that appear in the breadcrumb trail.
            # They have no links and are just labels. Only skip if they appear
            # within the pre-heading region and are short (<= 40 chars, no links).
            # Two formats: plain text ("Card") or bullet + text ("* Card")
            if (
                len(stripped) <= 40
                and stripped
                and not stripped.startswith("[")
                and not stripped.startswith("!")
                and not stripped.startswith("-")
                and not re.match(r'^\* \[.*?\]\(', stripped)
                and not re.match(r'^\* \[\]', stripped)
                # Allow removal of "* plain text" breadcrumb labels
            ):
                # Strip leading "* " for pure-text breadcrumb labels
                label = stripped
                if label.startswith("* "):
                    label = label[2:]
                # Skip if it's a short label with no markdown links
                if not re.search(r'\[.*?\]\(.*?\)', label) and len(label) <= 40:
                    continue
            pre_heading_kept.append(line)

    # --- Phase 3: Remove post-heading footer elements ---
    # Main content runs from heading until we hit footer markers.
    post_heading_lines = lines[heading_idx:] if heading_idx is not None else lines
    content_kept: list[str] = []
    in_footer = False

    for line in post_heading_lines:
        stripped = line.strip()

        if in_footer:
            continue

        # Prev/Next nav link signals start of footer
        # Pattern: [Previous ...](url)[Next ...](url) - may be standalone or
        # embedded in a longer line (e.g., appended to content on same line)
        if re.search(r'\[Previous .+?\]\(.+?\)\[Next .+?\]\(.+?\)', stripped):
            # If the prev/next pattern is the entire line, enter footer mode
            if re.match(r'^\[Previous .+?\]\(.+?\)\[Next .+?\]\(.+?\)', stripped):
                in_footer = True
                continue
            # If embedded in content, strip the prev/next portion from the line
            cleaned_line = re.sub(
                r'\[Previous .+?\]\(.+?\)\[Next .+?\]\(.+?\)',
                '',
                line,
            ).strip()
            if cleaned_line:
                content_kept.append(cleaned_line)
            continue
        if re.match(r'^\[Previous .+?\]\(.+?\)$', stripped):
            in_footer = True
            continue
        if re.match(r'^\[Next .+?\]\(.+?\)$', stripped):
            in_footer = True
            continue

        # Footer logo line also signals start of footer
        # Pattern:   * [ ![4ga Boards](...) ](https://4gaboards.com)
        if re.match(r'^\* \[ ?!\[4ga Boards\]', stripped):
            in_footer = True
            continue

        # Bottom TOC anchor links (point to #anchors on the same page)
        # Pattern: * [Section](url#anchor) (after stripping)
        if re.match(r'^\* \[.+?\]\(https://docs\.4gaboards\.com/docs/.+?#.+?\)', stripped):
            continue

        # Footer section headers near the end
        if stripped in ("Community", "Docs"):
            # These only appear in the footer at the very bottom
            remaining_from_this_line = len(post_heading_lines) - post_heading_lines.index(line)
            if remaining_from_this_line <= 20:
                in_footer = True
                continue

        # Copyright line
        if re.match(r'^© \d{4}', stripped):
            continue

        # "Edit this page" link
        if "Edit this page" in stripped:
            continue

        content_kept.append(line)

    # Combine: pre-heading should be empty after filtering, plus content
    result_lines = pre_heading_kept + content_kept

    # --- Phase 4: Clean up excessive blank lines (3+ consecutive -> 2) ---
    cleaned: list[str] = []
    blank_count = 0
    for line in result_lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                cleaned.append(line)
        else:
            blank_count = 0
            cleaned.append(line)

    result = "\n".join(cleaned).strip()
    removed_chars = len(content) - len(result)
    if removed_chars > 0:
        logger.debug(
            f"Filtered {removed_chars} chars of nav/sidebar/footer from {url}"
        )

    return result


def _is_nav_sidebar_line(line: str) -> bool:
    """Check if a line is a navigation, sidebar, or language-switcher element.

    These are lines that appear before the main # heading in
    Docusaurus-generated markdown and are always boilerplate.
    Accepts the full line (with leading whitespace preserved).
    """
    stripped = line.strip()

    # "Skip to main content" link
    if stripped.startswith("[Skip to main content]"):
        return True

    # Navbar: logo image link followed by section navigation links
    # Pattern: [ ![4ga Boards Documentation](url) ](url)[Getting Started](url)...
    # Key identifier: starts with [ ![ and contains ](url)[ pattern
    if re.match(r'^\[ ?!\[', stripped) and re.search(r'\]\(https?://.+?\)\[', stripped):
        return True

    # Language toggle anchor: [](https://docs.4gaboards.com/...)
    if re.match(r'^\[\]\(https://docs\.4gaboards\.com/', stripped):
        return True

    # Language switcher: * [English](url) or * [Polski](url)
    # (leading whitespace stripped, so pattern starts with *)
    if re.match(r'^\* \[English\]\(', stripped):
        return True
    if re.match(r'^\* \[Polski\]\(', stripped):
        return True

    # Sidebar TOC: indented link list items
    # Pattern: * [Topic](url) (with or without leading whitespace)
    # These are ALWAYS sidebar navigation regardless of what URL they point to
    # (some links point to docs.4gaboards.com, others to 4gaboards.com, etc.)
    if re.match(r'^\* \[.+?\]\(https?://', stripped):
        return True

    # Breadcrumb empty anchor: * [](url)
    if re.match(r'^\* \[\]\(https?://', stripped):
        return True

    return False


async def _discover_urls(base_url: str) -> list[str]:
    """发现所有需要爬取的页面URL。

    优先从三个核心手册入口爬取：
    - /docs/user-manual (用户手册)
    - /docs/admin-manual (管理员手册)
    - /docs/developer-manual (开发者手册)

    然后通过sitemap补充缺失的子页面。
    过滤掉安装部署类文档（install/docker/k8s/manual/uninstall等），
    只保留功能使用类文档。
    """
    # 从sitemap获取完整URL列表，再过滤
    sitemap_urls = await _fetch_sitemap_urls(base_url)

    # 过滤规则：排除安装部署类文档和无关页面
    skip_patterns = [
        "/docs/dev/docker",               # Docker 部署文档
        "/docs/dev/install",              # 安装文档
        "/docs/dev/manual-install",       # 手动安装文档
        "/docs/dev/k8s",                  # Kubernetes 部署文档
        "/docs/dev/uninstall",            # 卸载文档
        "/docs/dev/upgrade",              # 升级文档
        "/docs/dev/migration",            # 迁移文档
        "/docs/dev/contributing",         # 贡献者指南
        "/docs/dev/architecture",         # 架构文档
        "/docs/dev/web-server-config",    # Nginx/Apache/Caddy 服务器配置
        "/docs/dev/developers-additional",# 开发者额外信息（日志/Fail2Ban等）
        "/docs/dev/notifications",        # 开发者视角的通知配置（SMTP等）
        "/docs/dev/backup-restore",       # 备份恢复运维
        "/docs/dev/development",          # 开发者入口页
        "/docs/getting-started",          # 章节入口页（纯链接目录）
        "/docs/user-manual",              # 章节入口页
        "/docs/admin-manual",             # 竑节入口页
        "/docs/developer-manual",         # 章节入口页
        "/docs/additional",               # 不相关内容
        "/docs/additional-info",          # 不相关内容
        "/docs/donate",                   # 不相关内容
        "/blog",                          # 博客
        "/search",                        # 搜索
        "/pl/",                           # 波兰语版本
    ]

    # /docs/dev/ 下保留的URL（功能性文档，不排除）
    dev_keep_patterns = [
        "/docs/dev/api",                  # API 使用文档
        "/docs/dev/sso",                  # SSO 单点登录功能
    ]

    filtered_urls = []
    for url in sitemap_urls:
        # /docs/dev/ 下的保留URL不跳过
        is_dev_keep = any(pattern in url for pattern in dev_keep_patterns)
        if is_dev_keep:
            filtered_urls.append(url)
            continue

        # 检查是否应该跳过
        should_skip = False
        for pattern in skip_patterns:
            if pattern in url:
                should_skip = True
                break

        if should_skip:
            continue

        # 跳过首页（纯链接目录）
        if url.rstrip("/") == base_url.rstrip("/"):
            continue

        # 只保留 /docs/ 路径下的功能文档
        if "/docs/" in url:
            filtered_urls.append(url)

    # 不再添加入口页种子URL（它们本身是纯链接目录）

    # 去重
    filtered_urls = list(dict.fromkeys(filtered_urls))
    logger.info(f"过滤后保留 {len(filtered_urls)} 个功能文档URL（原始sitemap {len(sitemap_urls)} 个）")

    if filtered_urls:
        return filtered_urls

    # 如果过滤后为空，回退到从sitemap根页面提取链接
    logger.info("过滤后无URL，回退到从sitemap根页面提取链接")
    discovered = await _extract_links_from_root(base_url)
    # 再次过滤掉不相关页面
    discovered = [u for u in discovered if not any(p in u for p in skip_patterns)]
    return discovered if discovered else [base_url]


async def _fetch_sitemap_urls(base_url: str) -> list[str]:
    """Fetch and parse sitemap.xml from the documentation site."""
    sitemap_url = base_url.rstrip("/") + "/sitemap.xml"

    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.get(
                sitemap_url,
                timeout=aiohttp.ClientTimeout(total=15),
            )
            if resp.status != 200:
                logger.warning(f"Sitemap not found at {sitemap_url} (status {resp.status})")
                return []

            text = await resp.text()
            root = ET.fromstring(text)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            locs = root.findall(".//sm:loc", ns)
            if not locs:
                locs = root.findall(".//loc")

            urls = []
            base_domain = _extract_domain(base_url)
            for loc in locs:
                url = loc.text.strip() if loc.text else ""
                if url and _extract_domain(url) == base_domain:
                    # Skip non-doc pages (blog, search) and alternate language pages
                    if "/pl/" not in url and "/search" not in url:
                        urls.append(url)

            # Deduplicate
            urls = list(dict.fromkeys(urls))
            logger.info(f"Found {len(urls)} URLs in sitemap")
            return urls

    except Exception as exc:
        logger.warning(f"Failed to fetch sitemap: {exc}")
        return []


async def _extract_links_from_root(base_url: str) -> list[str]:
    """Crawl the root page and extract internal links as fallback URL discovery."""
    http_strategy = AsyncHTTPCrawlerStrategy()
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        word_count_threshold=5,
        exclude_external_links=True,
        verbose=False,
    )

    urls: list[str] = []

    try:
        async with AsyncWebCrawler(crawler_strategy=http_strategy) as crawler:
            result = await crawler.arun(url=base_url, config=run_config)
            if not result.success:
                logger.warning(f"Failed to crawl root page {base_url}")
                return [base_url]

            internal_links = _extract_internal_links(result, base_url)
            urls = [base_url] + internal_links
            # Deduplicate
            urls = list(dict.fromkeys(urls))

    except Exception as exc:
        logger.error(f"Link extraction failed: {exc}")
        urls = [base_url]

    return urls


def _extract_internal_links(result: object, base_url: str) -> list[str]:
    """Extract unique internal links from a crawl result, filtering to same domain."""
    links: list[str] = []
    if not result.links:
        return links

    internal = result.links.get("internal", [])
    seen = set()
    base_domain = _extract_domain(base_url)

    for link_info in internal:
        href = link_info.get("href", "") if isinstance(link_info, dict) else str(link_info)
        if not href or href in seen:
            continue
        if _extract_domain(href) == base_domain:
            # Skip alternate language pages and non-content pages
            if "/pl/" not in href and "/search" not in href:
                seen.add(href)
                links.append(href)

    return links


def _extract_domain(url: str) -> str:
    """Extract the domain from a URL for same-domain filtering."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc
    except Exception:
        return url


def _save_pages(pages: list[CrawledPage], output_dir: str) -> None:
    """Save crawled pages as JSON and individual markdown files."""
    manifest_path = os.path.join(output_dir, "manifest.json")
    manifest_data = [page.model_dump() for page in pages]
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, ensure_ascii=False, indent=2)

    md_dir = os.path.join(output_dir, "markdown")
    os.makedirs(md_dir, exist_ok=True)

    for i, page in enumerate(pages):
        safe_name = _url_to_filename(page.url, i)
        md_path = os.path.join(md_dir, f"{safe_name}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# {page.title}\n\n")
            f.write(f"Source: {page.url}\n\n")
            f.write(page.content)


def _url_to_filename(url: str, index: int) -> str:
    """Convert a URL to a safe filesystem filename."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "_") or "index"
    path = path[:80].replace(".", "_")
    return f"{index:03d}_{path}"


_SKIP_URL_PATTERNS = ["logo", "icon", "favicon", "avatar"]


def _image_url_to_filename(url: str, index: int) -> str:
    """Convert an image URL to a safe filesystem filename, preserving extension."""
    from urllib.parse import urlparse
    import hashlib
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "_") or "img"
    # Preserve original image extension
    ext = ""
    for candidate in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif"]:
        if path.lower().endswith(candidate):
            ext = candidate
            base = path[: -len(candidate)]
            break
    if not ext:
        # No known extension; use hash of URL + preserve last segment's ext if present
        dot_idx = path.rfind(".")
        if dot_idx > 0 and len(path) - dot_idx <= 5:
            ext = path[dot_idx:]
            base = path[:dot_idx]
        else:
            ext = ".png"
            base = path
    base = base[:60].replace(".", "_")
    # Append short hash to avoid collisions
    h = hashlib.md5(url.encode()).hexdigest()[:6]
    return f"{index:03d}_{base}_{h}{ext}"


async def _download_images(
    media: dict,
    base_url: str,
    images_dir: str,
) -> list[dict]:
    """Download same-domain images from a crawl result, returning metadata dicts.

    Filters out SVGs, small (<100 byte) images, and navigational elements.
    """
    base_domain = _extract_domain(base_url)
    raw_images = media.get("images", [])
    if not raw_images:
        return []

    # Filter images
    candidates: list[tuple[int, dict]] = []
    for img in raw_images:
        src = img.get("src", "")
        if not src:
            continue
        # Skip SVG
        if src.lower().endswith(".svg"):
            continue
        # Skip navigational elements
        src_lower = src.lower()
        if any(p in src_lower for p in _SKIP_URL_PATTERNS):
            continue
        # Same-domain check
        # Handle relative URLs by resolving against base_url
        if src.startswith("/"):
            from urllib.parse import urljoin
            src = urljoin(base_url, src)
        if _extract_domain(src) != base_domain:
            continue
        candidates.append((len(candidates), img))

    if not candidates:
        return []

    os.makedirs(images_dir, exist_ok=True)

    downloaded: list[dict] = []
    async with aiohttp.ClientSession() as session:
        for idx, img in candidates:
            src = img.get("src", "")
            if src.startswith("/"):
                from urllib.parse import urljoin
                src = urljoin(base_url, src)
            alt = img.get("alt", "")
            filename = _image_url_to_filename(src, idx)
            local_path = os.path.join(images_dir, filename)

            try:
                resp = await session.get(
                    src,
                    timeout=aiohttp.ClientTimeout(total=10),
                )
                if resp.status != 200:
                    continue
                data = await resp.read()
                # Skip tiny images (likely icons/spacers)
                if len(data) < 100:
                    continue
                with open(local_path, "wb") as f:
                    f.write(data)
                # Store path relative to output_dir parent
                rel_path = os.path.join("images", filename)
                downloaded.append({
                    "url": src,
                    "alt": alt,
                    "local_path": rel_path,
                })
            except Exception as exc:
                logger.debug(f"Failed to download image {src}: {exc}")
                continue

    return downloaded


def load_crawled_pages(output_dir: str) -> list[CrawledPage]:
    """Load previously crawled pages from the manifest file.

    Args:
        output_dir: Directory where crawled data was saved.

    Returns:
        List of CrawledPage objects.
    """
    manifest_path = os.path.join(output_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        logger.warning(f"No manifest found at {manifest_path}")
        return []

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [CrawledPage(**page_data) for page_data in data]