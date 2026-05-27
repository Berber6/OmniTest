"""Document parser and chunker for crawled markdown content."""

import json
import logging
import os
import uuid
from typing import Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .models import CrawledPage, DocumentChunk
from .crawler import load_crawled_pages

logger = logging.getLogger(__name__)

# Default chunking parameters per design spec
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200


def parse_and_chunk(
    docs_dir: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """Load crawled markdown documents, split into chunks, and return DocumentChunk objects.

    Args:
        docs_dir: Directory where crawled data was saved (contains manifest.json).
        chunk_size: Maximum size of each text chunk.
        chunk_overlap: Overlap between consecutive chunks.

    Returns:
        List of DocumentChunk objects ready for vector store ingestion.
    """
    pages = load_crawled_pages(docs_dir)
    if not pages:
        logger.warning(f"No crawled pages found in {docs_dir}")
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
        length_function=len,
    )

    chunks: list[DocumentChunk] = []

    for page in pages:
        page_chunks = _split_page(page, splitter)
        chunks.extend(page_chunks)

    logger.info(f"Parsed {len(pages)} pages into {len(chunks)} chunks")
    return chunks


def _split_page(
    page: CrawledPage,
    splitter: RecursiveCharacterTextSplitter,
) -> list[DocumentChunk]:
    """Split a single crawled page into DocumentChunk objects."""
    texts = splitter.split_text(page.content)

    chunks: list[DocumentChunk] = []
    for i, text in enumerate(texts):
        chunk_id = f"{_url_to_chunk_prefix(page.url)}_{i}"
        chunk = DocumentChunk(
            id=chunk_id,
            content=text,
            source_url=page.url,
            title=page.title,
            metadata={
                "chunk_index": i,
                "total_chunks_in_page": len(texts),
                "page_title": page.title,
            },
        )
        chunks.append(chunk)

    return chunks


def _url_to_chunk_prefix(url: str) -> str:
    """Convert a URL to a short, safe prefix for chunk IDs."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "_") or "index"
    path = path[:60].replace(".", "_")
    # Add a short hash to avoid collisions
    short_hash = uuid.uuid4().hex[:6]
    return f"{path}_{short_hash}"


def save_chunks(chunks: list[DocumentChunk], output_dir: str) -> None:
    """Save chunk data to a JSON file for later reference.

    Args:
        chunks: List of DocumentChunk objects.
        output_dir: Directory to save the chunks manifest.
    """
    os.makedirs(output_dir, exist_ok=True)
    chunks_path = os.path.join(output_dir, "chunks.json")
    data = [chunk.model_dump() for chunk in chunks]
    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(chunks)} chunks to {chunks_path}")


def load_chunks(output_dir: str) -> list[DocumentChunk]:
    """Load previously saved chunks from a JSON file.

    Args:
        output_dir: Directory containing chunks.json.

    Returns:
        List of DocumentChunk objects.
    """
    chunks_path = os.path.join(output_dir, "chunks.json")
    if not os.path.exists(chunks_path):
        logger.warning(f"No chunks manifest found at {chunks_path}")
        return []

    with open(chunks_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [DocumentChunk(**chunk_data) for chunk_data in data]