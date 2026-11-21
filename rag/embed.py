"""Text -> unit-length vectors through any OpenAI-compatible /v1/embeddings endpoint.

Configured in .env:
    EMBED_BASE_URL   empty = OpenAI; our GPU: http://localhost:8002/v1 (bge-m3 via the tunnel)
    EMBED_MODEL      text-embedding-3-small (default) or BAAI/bge-m3 on the GPU;
                     "hashing" = offline word-hash vectors (tests, demos without a key)
    EMBED_API_KEY    empty = use LLM_API_KEY
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Protocol

import numpy as np
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DEFAULT_MODEL = "text-embedding-3-small"
BATCH_SIZE = 64


class EmbeddingError(RuntimeError):
    """The embedding service is not configured or did not answer."""


class Embedder(Protocol):
    signature: str  # model + endpoint; stored with each vector so a switch triggers a rebuild

    def __call__(self, texts: list[str]) -> np.ndarray: ...


def normalize(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim == 1:
        vectors = vectors[None, :]
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


class OpenAIEmbedder:
    def __init__(self, model: str, base_url: str | None, api_key: str):
        from openai import OpenAI

        self.model = model
        self.signature = f"{model}@{base_url or 'openai'}"
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=60.0, max_retries=2)

    def __call__(self, texts: list[str]) -> np.ndarray:
        from openai import APIError

        out = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = [t if t.strip() else " " for t in texts[start:start + BATCH_SIZE]]
            try:
                resp = self._client.embeddings.create(model=self.model, input=batch)
            except APIError as exc:
                raise EmbeddingError(f"Embedding request failed ({self.signature}): {exc}") from exc
            out.extend(item.embedding for item in sorted(resp.data, key=lambda d: d.index))
        return normalize(np.array(out)) if out else np.zeros((0, 1), dtype=np.float32)


_TOKEN = re.compile(r"[a-z0-9]+|[一-鿿]", re.IGNORECASE)


class HashingEmbedder:
    """Bag-of-words vectors from hashed tokens (Chinese: one token per character).

    No network and no model: similar wording gives similar vectors. Good enough for tests
    and an offline demo, far weaker than a real embedding model.
    """

    def __init__(self, dims: int = 512):
        self.dims = dims
        self.signature = f"hashing-{dims}"

    def __call__(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dims), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in _TOKEN.findall(text.lower()):
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                vectors[row, int.from_bytes(digest, "little") % self.dims] += 1.0
        return normalize(vectors)


_default: Embedder | None = None


def get_embedder() -> Embedder:
    """The embedder configured in .env (created once per process)."""
    global _default
    if _default is None:
        model = os.getenv("EMBED_MODEL") or DEFAULT_MODEL
        if model == "hashing":
            _default = HashingEmbedder()
        else:
            key = os.getenv("EMBED_API_KEY") or os.getenv("LLM_API_KEY")
            if not key:
                raise EmbeddingError(
                    "No embedding key: set EMBED_API_KEY or LLM_API_KEY in .env "
                    "(or EMBED_MODEL=hashing for offline vectors)."
                )
            _default = OpenAIEmbedder(model, os.getenv("EMBED_BASE_URL") or None, key)
    return _default
