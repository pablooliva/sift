"""
Custom Vectors class for Ollama embeddings.

This module provides a txtai Vectors implementation that uses Ollama's
mxbai-embed-large model for embeddings, without loading any HuggingFace models.

Usage in config.yml:
    embeddings:
      method: custom_actions.ollama_vectors.OllamaVectors
      content: postgresql+psycopg2://...
      backend: qdrant_txtai.ann.qdrant.Qdrant
"""

import os
import logging
import re
import unicodedata
from typing import List

import numpy as np
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception,
    before_sleep_log,
)

from txtai.vectors import Vectors


def _is_transient_error(exception: BaseException) -> bool:
    """
    Determine if an exception is transient and should be retried.

    Retries:
    - Network errors (ConnectionError, Timeout)
    - Server errors (5xx HTTP status codes)

    Does NOT retry:
    - Client errors (4xx HTTP status codes) - bad input won't succeed on retry
    - Value errors (missing fields in response)
    """
    if isinstance(exception, requests.Timeout):
        return True
    if isinstance(exception, requests.ConnectionError):
        return True
    if isinstance(exception, requests.HTTPError):
        # Only retry 5xx server errors, not 4xx client errors
        if exception.response is not None:
            return exception.response.status_code >= 500
        return True  # Retry if we can't determine status
    return False

logger = logging.getLogger(__name__)

# Ollama configuration from environment
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
OLLAMA_EMBEDDINGS_MODEL = os.getenv("OLLAMA_EMBEDDINGS_MODEL", "nomic-embed-text")
# Embedding model dimensions - must match the model specified in OLLAMA_EMBEDDINGS_MODEL
# - nomic-embed-text: 768 dimensions, 8192 token context (recommended)
# - mxbai-embed-large: 1024 dimensions, 512 token context
# - bge-m3: 1024 dimensions, 8192 token context (has NaN bugs - avoid)
OLLAMA_EMBEDDING_DIMENSION = int(os.getenv("OLLAMA_EMBEDDING_DIMENSION", "768"))

# nomic-embed-text has context_length=8192 tokens
# Token-to-char ratio varies: ~4 chars/token for prose, ~2-3 for code/special chars
# This is a SAFETY NET for documents that bypass frontend chunking
# Frontend chunk size is 4000 chars; use slightly higher for safety margin
MAX_TEXT_CHARS = 8000  # ~2000-4000 tokens, safely within nomic-embed-text's 8192 limit


def sanitize_text_for_embedding(text: str) -> str:
    """
    Sanitize text to prevent NaN values in embeddings.

    Ollama's embedding models can produce NaN values when encountering:
    - NULL characters and other control characters
    - Malformed Unicode sequences
    - Empty or whitespace-only text
    - Excessive repetition of certain characters
    - Private use area Unicode characters
    - Surrogate characters

    Args:
        text: Raw input text

    Returns:
        Sanitized text safe for embedding, or placeholder if text is empty
    """
    if not text:
        return "[empty document]"

    # Normalize Unicode (NFC form - canonical composition)
    # This fixes malformed Unicode sequences
    try:
        text = unicodedata.normalize("NFC", text)
    except Exception:
        # If normalization fails, try to encode/decode with error handling
        text = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")

    # Remove problematic Unicode ranges that can cause NaN:
    # - Surrogate pairs (U+D800 to U+DFFF)
    # - Private use area (U+E000 to U+F8FF, U+F0000 to U+FFFFD, U+100000 to U+10FFFD)
    # - Non-characters (U+FDD0 to U+FDEF, U+FFFE, U+FFFF)
    cleaned_chars = []
    for char in text:
        code_point = ord(char)
        # Skip surrogate pairs
        if 0xD800 <= code_point <= 0xDFFF:
            continue
        # Skip private use areas
        if 0xE000 <= code_point <= 0xF8FF:
            continue
        if 0xF0000 <= code_point <= 0xFFFFD:
            continue
        if 0x100000 <= code_point <= 0x10FFFD:
            continue
        # Skip non-characters
        if 0xFDD0 <= code_point <= 0xFDEF:
            continue
        if code_point in (0xFFFE, 0xFFFF):
            continue
        cleaned_chars.append(char)
    text = "".join(cleaned_chars)

    # Remove NULL characters and other control characters (except newline, tab, carriage return)
    # Control characters are in categories Cc (control) and Cf (format)
    cleaned_chars = []
    for char in text:
        category = unicodedata.category(char)
        # Keep normal characters, and only whitespace control chars (space, tab, newline, CR)
        if category != "Cc" or char in "\n\t\r":
            cleaned_chars.append(char)
    text = "".join(cleaned_chars)

    # Remove any remaining problematic characters (zero-width, etc.)
    # These are in Unicode category Cf (format characters)
    text = "".join(char for char in text if unicodedata.category(char) != "Cf")

    # Collapse excessive repetition of any single character (more than 10 in a row)
    # This can cause numerical instability in embeddings
    text = re.sub(r'(.)\1{10,}', r'\1\1\1\1\1', text)

    # Collapse excessive whitespace (more than 3 consecutive newlines or spaces)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    text = re.sub(r' {4,}', '   ', text)
    text = re.sub(r'\t{3,}', '\t\t', text)

    # Collapse long runs of punctuation/symbols (e.g., "======" or "------")
    text = re.sub(r'[-=_*#~`]{6,}', lambda m: m.group(0)[0] * 5, text)

    # Strip leading/trailing whitespace
    text = text.strip()

    # If text is now empty, return placeholder
    if not text:
        return "[empty document after sanitization]"

    return text


class OllamaVectors(Vectors):
    """
    Custom Vectors implementation for Ollama embeddings.

    This class provides txtai with embedding capabilities using Ollama's API
    without requiring any HuggingFace model to be loaded.
    """

    def __init__(self, config=None, scoring=None, models=None):
        """
        Initialize the Ollama vectors model.

        Args:
            config: Embeddings configuration dict
            scoring: Scoring instance (optional, for txtai compatibility)
            models: Models cache (optional, for txtai compatibility)
        """
        # Set dimensions before calling super().__init__
        config = config or {}
        config['dimensions'] = OLLAMA_EMBEDDING_DIMENSION

        super().__init__(config, scoring, models)
        logger.info(f"Initialized OllamaVectors with dimension {OLLAMA_EMBEDDING_DIMENSION}")

    def loadmodel(self, path):
        """Load model - not needed for Ollama (returns None)."""
        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(min=1, max=10),
        retry=retry_if_exception(_is_transient_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _embed_single_text(self, text: str, api_url: str) -> List[float]:
        """
        Generate embedding for a single text with automatic retry.

        Args:
            text: Text to embed
            api_url: Ollama API URL for embeddings

        Returns:
            List of floats representing the embedding

        Raises:
            RuntimeError: If all retries exhausted or non-retryable error
        """
        # Truncate to prevent "input length exceeds context length" errors
        if len(text) > MAX_TEXT_CHARS:
            logger.warning(f"Truncating text from {len(text)} to {MAX_TEXT_CHARS} chars for embedding")
            text = text[:MAX_TEXT_CHARS]

        response = requests.post(
            api_url,
            json={
                "model": OLLAMA_EMBEDDINGS_MODEL,
                "prompt": text
            },
            timeout=30
        )

        # Log detailed error info before raising
        if response.status_code >= 400:
            text_preview = repr(text[:500]) if len(text) > 500 else repr(text)
            logger.error(f"Ollama API error: status={response.status_code}, body={response.text[:500]}")
            logger.error(f"Problematic text ({len(text)} chars): {text_preview}")

        response.raise_for_status()

        result = response.json()
        if "embedding" not in result:
            raise ValueError(f"Missing 'embedding' field in response")

        embedding = result["embedding"]

        # Validate embedding doesn't contain NaN or Inf values
        embedding_array = np.array(embedding, dtype=np.float32)
        if np.any(np.isnan(embedding_array)) or np.any(np.isinf(embedding_array)):
            # Log a sample of the problematic text for debugging
            text_preview = text[:200] if len(text) > 200 else text
            logger.error(f"Ollama returned NaN/Inf embedding. Text preview: {repr(text_preview)}")
            raise ValueError("Ollama returned embedding with NaN or Inf values")

        return embedding

    def encode(self, data, category=None):
        """
        Generate embeddings for input data using Ollama API.

        Args:
            data: List of texts or tuples to embed
            category: Category for encoding (optional, ignored)

        Returns:
            np.ndarray: Array of embeddings with shape (n_texts, 1024)
        """
        if not data:
            return np.array([], dtype=np.float32)

        # If data is already embeddings (numpy array), just cast and return
        if isinstance(data[0], np.ndarray):
            return np.array(data, dtype=np.float32)

        # Handle tuple inputs (id, text, tags) from txtai
        texts = []
        for item in data:
            if isinstance(item, tuple):
                text = str(item[1])
            else:
                text = str(item)

            # Sanitize text to prevent NaN errors from Ollama
            original_text = text
            text = sanitize_text_for_embedding(text)
            if len(text) != len(original_text):
                logger.debug(f"Text sanitized: {len(original_text)} -> {len(text)} chars")

            # Safety truncation for edge cases - chunks should already be ~1500 chars
            # This is a fallback for non-chunked docs or disabled chunking
            original_len = len(text)
            if original_len > MAX_TEXT_CHARS:
                logger.warning(f"Text exceeds {MAX_TEXT_CHARS} chars ({original_len}), truncating. "
                              "Consider enabling document chunking for better search quality.")
                text = text[:MAX_TEXT_CHARS]
            texts.append(text)

        print(f"[OllamaVectors] Generating embeddings for {len(texts)} texts, first text len: {len(texts[0]) if texts else 0}", flush=True)

        embeddings = []
        api_url = f"{OLLAMA_API_URL}/api/embeddings"

        for i, text in enumerate(texts):
            try:
                # Use retry-decorated method for automatic retry on transient errors
                embedding = self._embed_single_text(text, api_url)
                embeddings.append(embedding)

                if (i + 1) % 10 == 0:
                    logger.info(f"Generated {i + 1}/{len(texts)} embeddings")

            except requests.Timeout:
                raise RuntimeError(f"Ollama API timeout at {OLLAMA_API_URL} after 3 retries (text {i+1}/{len(texts)})")
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code < 500:
                    # 4xx error - client error, not retried
                    raise RuntimeError(f"Ollama API client error (HTTP {e.response.status_code}) for text {i+1}/{len(texts)}: {e}")
                raise RuntimeError(f"Ollama API server error after 3 retries for text {i+1}/{len(texts)}: {e}")
            except requests.RequestException as e:
                raise RuntimeError(f"Ollama API error after 3 retries for text {i+1}/{len(texts)}: {e}")

        embeddings_array = np.array(embeddings, dtype=np.float32)
        logger.info(f"Generated {len(embeddings)} embeddings with shape {embeddings_array.shape}")

        return embeddings_array
