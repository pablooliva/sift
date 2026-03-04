"""
Ollama-based embeddings transform module for txtai.

Part of SPEC-019 Phase 3: Migrate embeddings from BGE-Large to Ollama mxbai-embed-large.
This module provides a custom transform function for generating text embeddings using
Ollama's mxbai-embed-large model.

Usage in config.yml:
    embeddings:
      path: sentence-transformers/all-MiniLM-L6-v2  # Placeholder (not used, but required by txtai)
      functions: [custom_actions.ollama_embeddings.transform]
      content: postgresql+psycopg2://...
      backend: qdrant_txtai.ann.qdrant.Qdrant

This follows txtai's custom transform function pattern for embeddings:
https://neuml.github.io/txtai/embeddings/configuration/vectors/#external-vectors
"""

import os
import logging
from typing import List, Union

import numpy as np
import requests

logger = logging.getLogger(__name__)

# Ollama configuration from environment
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
OLLAMA_EMBEDDINGS_MODEL = os.getenv("OLLAMA_EMBEDDINGS_MODEL", "mxbai-embed-large")


def transform(inputs: List[Union[str, tuple]]) -> np.ndarray:
    """
    Generate embeddings for input texts using Ollama API.

    This function is called by txtai's embeddings pipeline to generate vector
    representations of text. It replaces the default transformer-based embeddings
    with Ollama's mxbai-embed-large model.

    Args:
        inputs: List of texts to embed. Each item can be:
               - str: Plain text
               - tuple: (id, text, tags) from txtai pipeline

    Returns:
        np.ndarray: Array of embeddings with shape (n_texts, embedding_dim)
                   where embedding_dim is 1024 for mxbai-embed-large

    Raises:
        requests.RequestException: If Ollama API is unavailable
        ValueError: If API returns invalid response
    """
    # Extract text from inputs (handle both string and tuple formats)
    texts = []
    for item in inputs:
        if isinstance(item, tuple):
            # txtai passes (id, text, tags) tuples during indexing
            texts.append(item[1])
        else:
            # Direct string input
            texts.append(str(item))

    if not texts:
        logger.warning("Empty input list provided to embeddings transform")
        return np.array([])

    logger.info(f"Generating embeddings for {len(texts)} texts using Ollama {OLLAMA_EMBEDDINGS_MODEL}")

    embeddings = []
    api_url = f"{OLLAMA_API_URL}/api/embeddings"

    for i, text in enumerate(texts):
        try:
            # Call Ollama embeddings API
            response = requests.post(
                api_url,
                json={
                    "model": OLLAMA_EMBEDDINGS_MODEL,
                    "prompt": text
                },
                timeout=30  # 30s timeout for embeddings generation
            )
            response.raise_for_status()

            result = response.json()

            # Extract embedding from response
            if "embedding" not in result:
                raise ValueError(f"Ollama API response missing 'embedding' field: {result}")

            embedding = result["embedding"]
            embeddings.append(embedding)

            # Log progress for large batches
            if (i + 1) % 10 == 0:
                logger.info(f"Generated {i + 1}/{len(texts)} embeddings")

        except requests.Timeout:
            logger.error(f"Timeout calling Ollama API for text {i+1}/{len(texts)}")
            raise RuntimeError(
                f"Ollama embeddings API timed out. Check if Ollama is running at {OLLAMA_API_URL}"
            )

        except requests.RequestException as e:
            logger.error(f"Error calling Ollama API: {e}")
            raise RuntimeError(
                f"Failed to connect to Ollama at {OLLAMA_API_URL}. "
                f"Ensure Ollama is running and accessible. Error: {e}"
            )

        except (KeyError, ValueError) as e:
            logger.error(f"Invalid response from Ollama API: {e}")
            raise ValueError(f"Ollama API returned invalid response: {e}")

    # Convert to numpy array
    embeddings_array = np.array(embeddings, dtype=np.float32)

    logger.info(
        f"Successfully generated {len(embeddings)} embeddings "
        f"with shape {embeddings_array.shape}"
    )

    return embeddings_array


def get_dimension() -> int:
    """
    Get the embedding dimension for the configured Ollama model.

    This is used by txtai to determine the vector dimension for storage.

    Returns:
        int: Embedding dimension (1024 for mxbai-embed-large)
    """
    # mxbai-embed-large produces 1024-dimensional embeddings
    # This matches BGE-Large's dimension, so no schema changes needed
    return 1024
