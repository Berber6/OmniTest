"""Image index for connecting crawled images to the RAG pipeline.

Builds an in-memory mapping from source page URLs to their associated images,
using the manifest.json produced by the crawler. This enables:
1. Adding image references to ChromaDB chunk metadata
2. Providing image context to the scenario generation prompt
3. Loading reference images for visual_match verification
"""

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ImageRef(BaseModel):
    """Reference to a crawled image associated with a page."""

    url: str = Field(..., description="Original URL of the image")
    alt: str = Field(default="", description="Alt text from the crawled page")
    local_path: str = Field(..., description="Relative path like 'images/000_...png'")
    source_page_url: str = Field(default="", description="URL of the page where this image appeared")
    source_page_title: str = Field(default="", description="Title of that page")


class ImageStore:
    """In-memory image index built from the crawl manifest."""

    _by_url: dict[str, list[ImageRef]] = {}  # page_url -> [ImageRef]
    _by_path: dict[str, ImageRef] = {}  # local_path -> ImageRef
    _all: list[ImageRef] = []

    @classmethod
    def build_from_manifest(cls, manifest_path: str) -> None:
        """Build the index from a crawl manifest JSON file."""
        path = Path(manifest_path)
        if not path.exists():
            logger.warning(f"Manifest not found at {manifest_path}")
            return

        with open(path, "r", encoding="utf-8") as f:
            pages = json.load(f)

        cls._by_url = {}
        cls._by_path = {}
        cls._all = []

        for page in pages:
            page_url = page.get("url", "")
            page_title = page.get("title", "")
            images = page.get("images", [])

            refs = []
            for img in images:
                ref = ImageRef(
                    url=img.get("url", ""),
                    alt=img.get("alt", ""),
                    local_path=img.get("local_path", ""),
                    source_page_url=page_url,
                    source_page_title=page_title,
                )
                refs.append(ref)
                cls._by_path[ref.local_path] = ref
                cls._all.append(ref)

            cls._by_url[page_url] = refs

        logger.info(f"ImageStore indexed {len(cls._all)} images from {len(cls._by_url)} pages")

    @classmethod
    def get_images_for_url(cls, url: str) -> list[ImageRef]:
        """Get all images associated with a crawled page URL."""
        return cls._by_url.get(url, [])

    @classmethod
    def get_image_by_path(cls, local_path: str) -> Optional[ImageRef]:
        """Get a specific image by its local_path."""
        return cls._by_path.get(local_path)

    @classmethod
    def get_all_images(cls) -> list[ImageRef]:
        """Get all indexed images."""
        return cls._all

    @classmethod
    def format_for_prompt(cls, images: list) -> str:
        """Format image references for inclusion in LLM prompt.

        Accepts both ImageRef objects and plain dicts (from chunk metadata).
        """
        if not images:
            return "暂无参考截图可用。"

        lines = ["## 参考截图（来自爬取的文档页面）"]
        for img in images:
            # Support both ImageRef objects and plain dicts
            alt = img.alt if hasattr(img, 'alt') else img.get("alt", "")
            local_path = img.local_path if hasattr(img, 'local_path') else img.get("local_path", "")
            source_page = img.source_page_title if hasattr(img, 'source_page_title') else img.get("source_page_title", "")
            desc = alt if alt else "无描述"
            lines.append(f"- [{desc}] 路径: {local_path} (来源页面: {source_page})")
        return "\n".join(lines)