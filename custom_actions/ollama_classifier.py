"""
Ollama-based document classification module for txtai workflows.

Part of SPEC-019 Phase 1: Migrate labels classification from BART-MNLI to Ollama.
This module provides a custom workflow action for document classification using
Ollama's llama3.2-vision:11b model.

Usage in config.yml:
    workflow:
      ollama-labels:
        tasks:
          - action: custom_actions.ollama_classifier.classify
            args: [["reference", "analysis", "technical", "strategic", "meeting-notes", "actionable", "status"]]

This follows txtai's custom workflow action pattern:
https://neuml.github.io/txtai/workflow/task/
"""

import os
import re
import json
import logging
from typing import List, Dict, Any

import requests

logger = logging.getLogger(__name__)


def classify(text, labels: List[str] = None) -> str:
    """
    Classify text into one of the provided categories using Ollama LLM.

    This function is designed to be called by txtai workflows as a custom action.
    It performs zero-shot classification using Ollama's llama3.2-vision:11b model.

    Args:
        text: Text content to classify (may be a string or single-element list from workflow)
        labels: List of candidate labels (categories)

    Returns:
        str: The predicted category name

    Raises:
        ValueError: If text is empty or labels are not provided
        requests.exceptions.RequestException: If Ollama API call fails

    Example:
        >>> classify("API documentation for REST endpoints",
        ...          ["reference", "analysis", "technical"])
        'reference'
    """
    # Get Ollama configuration from environment
    ollama_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_CLASSIFICATION_MODEL", "llama3.2-vision:11b")

    # txtai workflows may pass text as a single-element list or string
    if isinstance(text, list):
        if len(text) == 0:
            raise ValueError("Text list is empty")
        text = text[0]

    # Validate inputs
    if not text or not isinstance(text, str) or not text.strip():
        raise ValueError("Text cannot be empty")

    if not labels or not isinstance(labels, list) or len(labels) == 0:
        raise ValueError("Labels list is required and cannot be empty")

    # Sanitize text
    text = text.strip()

    # Truncate if too long (10K chars max)
    if len(text) > 10000:
        text = text[:10000]
        logger.info("Truncated text to 10,000 characters for classification")

    # Remove control characters except newlines and tabs
    text = ''.join(char for char in text if char.isprintable() or char in '\n\t')

    # Build classification prompt with clear category descriptions
    prompt = f"""Classify this document into exactly ONE category. Choose the single best match.

Categories and their meanings:
- reference: Guides, specifications, documentation, APIs, how-to articles (things you look up for information)
- analysis: Research findings, investigations, root cause analysis, performance analysis (your thinking and conclusions)
- technical: Source code, infrastructure configuration, implementation details, architecture diagrams
- strategic: Product roadmaps, business plans, vision documents, long-term goals, strategic initiatives
- meeting-notes: Records of meetings, discussions, attendees, decisions made in meetings
- actionable: TODOs, tasks, urgent items, follow-ups, action items requiring immediate attention
- status: Progress reports, status updates, completion percentages, current state of work

Document to classify:
\"\"\"
{text}
\"\"\"

Think step by step:
1. What is the primary purpose of this document?
2. Who would use this document and why?
3. Which category best matches that purpose?

Respond with ONLY the category name (one word).
Category:"""

    # Call Ollama API
    logger.info(f"Calling Ollama for classification: {ollama_url}/api/generate")

    try:
        response = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Low temperature for deterministic classification
                    "top_p": 0.9
                }
            },
            timeout=30  # 30s timeout for cold-start (SPEC-019 RISK-001)
        )
        response.raise_for_status()

        # Parse Ollama response
        result = response.json()
        llm_response = result.get("response", "").strip()

        if not llm_response:
            logger.warning("Empty response from Ollama, defaulting to first label")
            return labels[0]

        # Extract category from LLM response
        category = _extract_category(llm_response, labels)

        logger.info(f"Classified as: {category} (LLM response: '{llm_response}')")
        # Return as single-element list to prevent txtai from iterating over string characters
        return [category]

    except requests.exceptions.Timeout:
        logger.error(f"Ollama classification timeout (likely model loading)")
        raise

    except requests.exceptions.ConnectionError as e:
        logger.error(f"Cannot connect to Ollama at {ollama_url}: {e}")
        raise

    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            logger.error(f"Model '{ollama_model}' not found. Run: ollama pull {ollama_model}")
        raise

    except Exception as e:
        logger.error(f"Unexpected error during classification: {e}")
        raise


def classify_with_scores(text, default_labels: List[str] = None, allow_custom: bool = True) -> List[Dict[str, Any]]:
    """
    Classify text with confidence scores for all default labels, plus optional custom suggestions.

    This function provides comprehensive classification suitable for UI preview:
    - Returns confidence scores (0.0-1.0) for ALL default labels
    - Optionally suggests additional custom labels beyond the default set
    - Designed for document preview workflow where users review AI suggestions

    Args:
        text: Text content to classify (may be a string or single-element list from workflow)
        default_labels: List of default category labels to score
        allow_custom: Whether to allow LLM to suggest additional custom labels (default True)

    Returns:
        List[Dict]: List of label dictionaries, each with:
            - label: str (label name)
            - score: float (confidence 0.0-1.0)
            - custom: bool (True if LLM-suggested, False if from default_labels)

    Raises:
        ValueError: If text is empty or labels are not provided
        requests.exceptions.RequestException: If Ollama API call fails

    Example:
        >>> classify_with_scores(
        ...     "Python tutorial on async programming",
        ...     ["reference", "analysis", "technical"],
        ...     allow_custom=True
        ... )
        [
            {"label": "reference", "score": 0.85, "custom": False},
            {"label": "technical", "score": 0.75, "custom": False},
            {"label": "analysis", "score": 0.15, "custom": False},
            {"label": "tutorial", "score": 0.90, "custom": True}
        ]
    """
    # Get Ollama configuration from environment
    ollama_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_CLASSIFICATION_MODEL", "llama3.2-vision:11b")

    # txtai workflows may pass text as a single-element list or string
    if isinstance(text, list):
        if len(text) == 0:
            raise ValueError("Text list is empty")
        text = text[0]

    # Validate inputs
    if not text or not isinstance(text, str) or not text.strip():
        raise ValueError("Text cannot be empty")

    if not default_labels or not isinstance(default_labels, list) or len(default_labels) == 0:
        raise ValueError("default_labels list is required and cannot be empty")

    # Sanitize text
    text = text.strip()

    # Truncate if too long (10K chars max)
    if len(text) > 10000:
        text = text[:10000]
        logger.info("Truncated text to 10,000 characters for classification")

    # Remove control characters except newlines and tabs
    text = ''.join(char for char in text if char.isprintable() or char in '\n\t')

    # Build comprehensive classification prompt
    labels_list = "\n".join([f"- {label}" for label in default_labels])

    custom_instruction = ""
    if allow_custom:
        custom_instruction = """
4. Suggest 0-2 additional custom labels if the document has important characteristics
   not captured by the default labels (e.g., "tutorial", "meeting-notes", "urgent").
   Custom labels should be single words or hyphenated phrases."""

    prompt = f"""Analyze this document and provide confidence scores for ALL default labels.

Default Labels to Score (0-100%):
{labels_list}

Document to classify:
\"\"\"
{text}
\"\"\"

Think step by step:
1. What is the primary purpose and content of this document?
2. For EACH default label, estimate confidence (0-100%) that it applies
3. Be specific - don't give everything high scores{custom_instruction}

Respond in this EXACT format (JSON):
{{
  "default_scores": {{
    {", ".join([f'"{label}": <0-100>' for label in default_labels])}
  }},
  "custom_labels": [
    {{"label": "<custom_label_1>", "score": <0-100>}},
    {{"label": "<custom_label_2>", "score": <0-100>}}
  ]
}}

Only include custom_labels if you have strong suggestions (score >= 70). Otherwise use empty list.
JSON Response:"""

    # Call Ollama API
    logger.info(f"Calling Ollama for multi-label classification: {ollama_url}/api/generate")

    try:
        response = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Low temperature for deterministic classification
                    "top_p": 0.9
                }
            },
            timeout=30  # 30s timeout for cold-start
        )
        response.raise_for_status()

        # Parse Ollama response
        result = response.json()
        llm_response = result.get("response", "").strip()

        if not llm_response:
            logger.warning("Empty response from Ollama, returning default scores")
            return _create_default_scores(default_labels)

        # Extract JSON from LLM response
        classification_result = _parse_classification_json(llm_response, default_labels, allow_custom)

        logger.info(f"Multi-label classification complete: {len(classification_result)} labels")

        # Return as JSON string wrapped in list (prevents txtai from iterating over string chars)
        # API client will parse result[0] as JSON to get the label list
        return [json.dumps({"labels": classification_result})]

    except requests.exceptions.Timeout:
        logger.error(f"Ollama classification timeout (likely model loading)")
        raise

    except requests.exceptions.ConnectionError as e:
        logger.error(f"Cannot connect to Ollama at {ollama_url}: {e}")
        raise

    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            logger.error(f"Model '{ollama_model}' not found. Run: ollama pull {ollama_model}")
        raise

    except Exception as e:
        logger.error(f"Unexpected error during classification: {e}")
        raise


def _parse_classification_json(llm_response: str, default_labels: List[str], allow_custom: bool) -> List[Dict[str, Any]]:
    """
    Parse LLM JSON response into structured label list.

    Args:
        llm_response: Raw text response from LLM (should contain JSON)
        default_labels: List of default labels to expect
        allow_custom: Whether custom labels are allowed

    Returns:
        List[Dict]: Parsed label scores with "label", "score", "custom" keys
    """
    import json

    try:
        # Extract JSON from response (LLM might add text before/after)
        json_match = re.search(r'\{[\s\S]*\}', llm_response)
        if not json_match:
            logger.warning("No JSON found in LLM response, using defaults")
            return _create_default_scores(default_labels)

        json_str = json_match.group(0)
        parsed = json.loads(json_str)

        # Extract default label scores
        default_scores = parsed.get("default_scores", {})
        results = []

        for label in default_labels:
            score = default_scores.get(label, 0)
            # Normalize to 0.0-1.0 range
            normalized_score = max(0.0, min(1.0, score / 100.0))
            results.append({
                "label": label,
                "score": normalized_score,
                "custom": False
            })

        # Extract custom label suggestions if allowed
        if allow_custom:
            custom_labels = parsed.get("custom_labels", [])
            if isinstance(custom_labels, list):
                for custom_item in custom_labels:
                    if isinstance(custom_item, dict) and "label" in custom_item and "score" in custom_item:
                        label = custom_item["label"].strip()
                        score = custom_item["score"]

                        # Skip if empty or already in default labels
                        if not label or label in default_labels:
                            continue

                        # Normalize score and add if meets threshold
                        normalized_score = max(0.0, min(1.0, score / 100.0))
                        if normalized_score >= 0.7:  # Only add high-confidence custom labels
                            results.append({
                                "label": label,
                                "score": normalized_score,
                                "custom": True
                            })

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)

        return results

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON from LLM: {e}, using defaults")
        return _create_default_scores(default_labels)
    except Exception as e:
        logger.warning(f"Error parsing classification response: {e}, using defaults")
        return _create_default_scores(default_labels)


def _create_default_scores(labels: List[str]) -> List[str]:
    """
    Create default equal-probability scores when LLM fails.

    Args:
        labels: List of label names

    Returns:
        Single-element list containing JSON string with labels
    """
    default_labels = [
        {"label": label, "score": 0.2, "custom": False}
        for label in labels
    ]
    # Return as JSON string wrapped in list for txtai workflow compatibility
    return [json.dumps({"labels": default_labels})]


def _extract_category(llm_response: str, labels: List[str]) -> str:
    """
    Extract category from LLM response text.

    Uses 3-level fallback strategy:
    1. Exact match (case-insensitive)
    2. Word search in response
    3. Default to first label

    Args:
        llm_response: Raw text response from LLM
        labels: List of valid labels

    Returns:
        str: Extracted category name
    """
    # Method 1: Check if response exactly matches a label (case-insensitive)
    for label in labels:
        if llm_response.lower() == label.lower():
            return label

    # Method 2: Look for label words in the response
    words = re.findall(r'\b\w+(?:-\w+)*\b', llm_response.lower())
    for word in words:
        for label in labels:
            if word == label.lower():
                return label

    # Method 3: Fallback - default to first label
    logger.warning(
        f"Could not extract valid category from LLM response: '{llm_response}', "
        f"defaulting to '{labels[0]}'"
    )
    return labels[0]
