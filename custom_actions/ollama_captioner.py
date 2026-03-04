"""
Ollama-based image captioning module for txtai workflows.

Part of SPEC-019 Phase 2: Migrate image captioning from BLIP-2 to Ollama.
This module provides a custom workflow action for image captioning using
Ollama's llama3.2-vision:11b model.

Usage in config.yml:
    workflow:
      ollama-caption:
        tasks:
          - action: custom_actions.ollama_captioner.caption

This follows txtai's custom workflow action pattern:
https://neuml.github.io/txtai/workflow/task/
"""

import os
import base64
import logging
from typing import List, Union

import requests

logger = logging.getLogger(__name__)


def caption(file_path: Union[str, List[str]]) -> List[str]:
    """
    Generate a natural language caption for an image using Ollama vision model.

    This function is designed to be called by txtai workflows as a custom action.
    It uses Ollama's llama3.2-vision:11b model for image captioning.

    Args:
        file_path: Path to image file (may be a string or single-element list from workflow)

    Returns:
        List[str]: Single-element list containing the caption (list format prevents
                   txtai from iterating over string characters)

    Raises:
        ValueError: If file_path is empty or invalid
        FileNotFoundError: If image file doesn't exist
        requests.exceptions.RequestException: If Ollama API call fails

    Example:
        >>> caption("/uploads/images/photo.jpg")
        ['A person standing on a mountain peak at sunset']
    """
    # Get Ollama configuration from environment
    ollama_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_VISION_MODEL", "llama3.2-vision:11b")

    # txtai workflows may pass file_path as a single-element list or string
    if isinstance(file_path, list):
        if len(file_path) == 0:
            raise ValueError("File path list is empty")
        file_path = file_path[0]

    # Validate input
    if not file_path or not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("File path cannot be empty")

    file_path = file_path.strip()

    # Security: Sanitize file path to prevent directory traversal
    if ".." in file_path or not file_path.startswith("/uploads/"):
        raise ValueError("Invalid file path. Files must be in /uploads directory.")

    # Check if file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Image file not found: {file_path}")

    # Read and encode image as base64
    try:
        with open(file_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to read image file {file_path}: {e}")
        raise ValueError(f"Cannot read image file: {e}")

    # Build captioning prompt
    prompt = """Describe this image in detail. Provide a clear, natural language description of:
- What you see in the image (objects, people, scenes, text)
- The setting or context
- Any notable details or activities

Be specific and descriptive. Write 1-2 sentences."""

    # Call Ollama Vision API
    logger.info(f"Calling Ollama vision API for captioning: {ollama_url}/api/generate")

    try:
        response = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": ollama_model,
                "prompt": prompt,
                "images": [image_data],
                "stream": False,
                "options": {
                    "temperature": 0.3,  # Slightly higher than classification for creativity
                    "top_p": 0.9
                }
            },
            timeout=30  # 30s timeout for cold-start (SPEC-019 RISK-001)
        )
        response.raise_for_status()

        # Parse Ollama response
        result = response.json()
        caption_text = result.get("response", "").strip()

        if not caption_text:
            logger.warning("Empty caption from Ollama, using default")
            caption_text = "An image"

        # Clean up caption
        caption_text = _clean_caption(caption_text)

        logger.info(f"Generated caption for {file_path}: {caption_text[:100]}...")

        # Return as single-element list to prevent txtai from iterating over string characters
        return [caption_text]

    except requests.exceptions.Timeout:
        logger.error(f"Ollama caption timeout (likely model loading)")
        raise

    except requests.exceptions.ConnectionError as e:
        logger.error(f"Cannot connect to Ollama at {ollama_url}: {e}")
        raise

    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            logger.error(f"Model '{ollama_model}' not found. Run: ollama pull {ollama_model}")
        raise

    except Exception as e:
        logger.error(f"Unexpected error during captioning: {e}")
        raise


def _clean_caption(caption: str) -> str:
    """
    Clean up caption text by removing repetitive patterns and formatting.

    Args:
        caption: Raw caption text from model

    Returns:
        str: Cleaned caption text
    """
    # Remove common repetitive patterns (model can get stuck in loops)
    # Example: "A cat. A cat. A cat." -> "A cat."
    words = caption.split()
    if len(words) > 3:
        # Check for 3+ consecutive repetitions
        cleaned_words = [words[0]]
        repetition_count = 1

        for i in range(1, len(words)):
            if words[i] == words[i-1]:
                repetition_count += 1
                if repetition_count <= 2:  # Allow up to 2 repetitions
                    cleaned_words.append(words[i])
            else:
                repetition_count = 1
                cleaned_words.append(words[i])

        caption = " ".join(cleaned_words)

    # Remove extra whitespace
    caption = " ".join(caption.split())

    # Ensure caption ends with punctuation
    if caption and caption[-1] not in ".!?":
        caption += "."

    # Capitalize first letter
    if caption:
        caption = caption[0].upper() + caption[1:]

    return caption
