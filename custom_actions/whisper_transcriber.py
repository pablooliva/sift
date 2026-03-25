"""
Lazy-loading Whisper transcriber for txtai workflows.

This custom workflow action provides on-demand Whisper model loading for
audio/video transcription, avoiding constant VRAM usage at startup.

Architecture:
- Load Whisper model only when transcription is requested
- Cache model for session duration to avoid repeated loading
- Model auto-unloads based on Docker container lifecycle and Whisper's internal caching

SPEC-019 Phase 4: Transcription Lazy Loading
- Replaces static transcription pipeline in config.yml
- Reduces idle VRAM by ~3 GB (Whisper large-v3 model)
- Maintains same API interface for frontend compatibility
"""

import logging
import os
from typing import Any, Dict, Optional

# txtai imports
from txtai.pipeline import Transcription

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global model cache (lazy-loaded singleton)
_transcription_model: Optional[Transcription] = None


def _load_model() -> Transcription:
    """
    Load Whisper transcription model (lazy initialization).

    Returns:
        Transcription: Loaded Whisper pipeline

    Raises:
        RuntimeError: If model loading fails
    """
    global _transcription_model

    if _transcription_model is not None:
        logger.debug("Using cached Whisper model")
        return _transcription_model

    logger.info("Loading Whisper model (lazy initialization)...")

    try:
        # Check WHISPER_GPU env var (default: true for backwards compatibility)
        use_gpu = os.environ.get("WHISPER_GPU", "true").lower() in ("true", "1", "yes")
        # Use smaller model on CPU for acceptable performance
        model_path = "openai/whisper-large-v3" if use_gpu else "openai/whisper-base"

        logger.info(f"Loading Whisper model: {model_path} (gpu={use_gpu})")
        _transcription_model = Transcription(
            path=model_path,
            gpu=use_gpu
        )
        logger.info("Whisper model loaded successfully")
        return _transcription_model

    except Exception as e:
        logger.error(f"Failed to load Whisper model: {e}")
        raise RuntimeError(f"Whisper model loading failed: {e}")


def transcribe(file_path: str, **kwargs) -> str:
    """
    Transcribe audio/video file using lazy-loaded Whisper model.

    This is the main workflow action function called by txtai workflows.

    Args:
        file_path (str): Path to audio/video file (must be accessible to container)
        **kwargs: Additional transcription parameters (chunk, join, etc.)

    Returns:
        str: Transcribed text

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is unsupported
        RuntimeError: If transcription fails

    Example:
        # In txtai workflow
        workflow:
          lazy-transcribe:
            tasks:
              - action: custom_actions.whisper_transcriber.transcribe
    """
    # txtai workflows may pass file_path as a single-element list or string
    if isinstance(file_path, list):
        if len(file_path) == 0:
            raise ValueError("File path list is empty")
        file_path = file_path[0]

    # Validate input
    if not file_path or not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("File path cannot be empty")

    file_path = file_path.strip()

    logger.info(f"Transcription requested for: {file_path}")

    # Validate file exists
    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    # Validate file is readable
    if not os.path.isfile(file_path):
        error_msg = f"Path is not a file: {file_path}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Security: Validate file path is within allowed directory
    # (files should be in /uploads/ directory for container access)
    if not file_path.startswith("/uploads/"):
        logger.warning(f"File outside /uploads/: {file_path}")
        # Don't block, but log for security audit

    try:
        # Lazy-load model (only loads on first call)
        model = _load_model()

        # Transcribe file
        logger.info(f"Transcribing file: {file_path}")
        transcription = model(file_path, **kwargs)

        # Handle empty transcription
        if not transcription or (isinstance(transcription, str) and not transcription.strip()):
            logger.warning(f"Empty transcription for {file_path} - file may be silent")
            return ""

        logger.info(f"Transcription complete: {len(transcription)} characters")

        # Return as tuple to prevent txtai workflow from iterating over string characters
        # txtai workflows iterate over return values; returning (result,) keeps it intact
        return (transcription,)

    except FileNotFoundError:
        # Re-raise file not found errors
        raise

    except Exception as e:
        error_msg = f"Transcription failed for {file_path}: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)


def unload_model() -> None:
    """
    Manually unload Whisper model to free VRAM.

    This function can be called explicitly if needed, but typically the model
    will remain cached for the container lifetime to avoid reload overhead.

    Note: txtai workflows don't have automatic idle timeout mechanisms,
    so this function is provided for explicit cleanup if needed.
    """
    global _transcription_model

    if _transcription_model is not None:
        logger.info("Unloading Whisper model...")
        _transcription_model = None
        logger.info("Whisper model unloaded")
    else:
        logger.debug("Whisper model was not loaded")


# Workflow action metadata (for txtai workflow system)
__all__ = ["transcribe", "unload_model"]
