"""ChromaDB vector store for document chunk storage and retrieval."""

import logging
import os
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions

from .models import DocumentChunk

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION_NAME = "4gaboards_docs"
DEFAULT_PERSIST_DIR = "data/chroma_db"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"


class VectorStore:
    """ChromaDB-based vector store for document chunk storage and retrieval."""

    def __init__(
        self,
        persist_dir: str = DEFAULT_PERSIST_DIR,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        """Initialize ChromaDB client with persistent storage and embedding function.

        Args:
            persist_dir: Directory for ChromaDB persistent storage.
            collection_name: Name of the ChromaDB collection.
            embedding_model: Sentence-transformers model name for embeddings.
        """
        os.makedirs(persist_dir, exist_ok=True)

        self._client = chromadb.PersistentClient(path=persist_dir)

        self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=embedding_model,
            **{"local_files_only": True},
        )

        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(
            f"Initialized VectorStore: collection='{collection_name}', "
            f"persist_dir='{persist_dir}', model='{embedding_model}', "
            f"existing_docs={self._collection.count()}"
        )

    def add_documents(self, chunks: list[DocumentChunk]) -> int:
        """Store document chunks as vectors in ChromaDB.

        Args:
            chunks: List of DocumentChunk objects to store.

        Returns:
            Number of chunks successfully added.
        """
        if not chunks:
            logger.warning("No chunks provided to add_documents")
            return 0

        ids = [chunk.id for chunk in chunks]
        documents = [chunk.content for chunk in chunks]
        metadatas = [
            {
                "source_url": chunk.source_url,
                "title": chunk.title,
                **chunk.metadata,
            }
            for chunk in chunks
        ]

        # Add in batches to avoid ChromaDB limits
        batch_size = 500
        total_added = 0

        for start in range(0, len(chunks), batch_size):
            end = start + batch_size
            batch_ids = ids[start:end]
            batch_docs = documents[start:end]
            batch_meta = metadatas[start:end]

            try:
                self._collection.upsert(
                    ids=batch_ids,
                    documents=batch_docs,
                    metadatas=batch_meta,
                )
                total_added += len(batch_ids)
            except Exception as exc:
                logger.error(f"Failed to add batch {start}-{end}: {exc}")
                continue

        logger.info(f"Added {total_added}/{len(chunks)} chunks to ChromaDB")
        return total_added

    def retrieve(
        self,
        query: str,
        n_results: int = 5,
        max_distance: float = 0.50,
    ) -> list[DocumentChunk]:
        """Retrieve relevant document chunks from ChromaDB for a query.

        Args:
            query: Search query text.
            n_results: Number of results to return.
            max_distance: Maximum cosine distance threshold; chunks above
                this are filtered out as low-relevance.
        """
        if not query.strip():
            logger.warning("Empty query provided to retrieve")
            return []

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(n_results, self._collection.count()),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.error(f"Query failed: {exc}")
            return []

        if not results or not results.get("ids") or not results["ids"][0]:
            return []

        chunks: list[DocumentChunk] = []
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i] if results["distances"] else None

            # Filter out low-relevance chunks
            if distance is not None and distance > max_distance:
                logger.debug(
                    f"Filtered low-relevance chunk {doc_id}: "
                    f"distance={distance:.4f} > threshold={max_distance}"
                )
                continue

            content = results["documents"][0][i]
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}

            source_url = metadata.get("source_url", "")
            title = metadata.get("title", "")

            # Remove fields we already extracted from metadata dict
            clean_meta = {
                k: v for k, v in metadata.items()
                if k not in ("source_url", "title")
            }
            # Include distance as relevance score
            if distance is not None:
                clean_meta["relevance_distance"] = distance

            chunk = DocumentChunk(
                id=doc_id,
                content=content,
                source_url=source_url,
                title=title,
                metadata=clean_meta,
            )
            chunks.append(chunk)

        return chunks

    def count(self) -> int:
        """Return the number of documents in the collection."""
        return self._collection.count()

    def reset(self) -> None:
        """Delete and recreate the collection (for re-indexing)."""
        name = self._collection.name
        self._client.delete_collection(name)
        self._collection = self._client.get_or_create_collection(
            name=name,
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"Reset collection '{name}'")