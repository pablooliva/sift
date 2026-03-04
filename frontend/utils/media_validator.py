"""
Media file validation utilities using ffprobe.

This module provides validation for audio and video files before transcription,
implementing EDGE-002 through EDGE-007 and FAIL-004 from SPEC-002.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple


class MediaValidator:
    """Validate media files using ffprobe before processing."""

    # Allowed audio codecs (EDGE-004: Unsupported codec detection)
    ALLOWED_AUDIO_CODECS = {
        "aac",
        "mp3",
        "pcm_s16le",  # WAV PCM
        "pcm_s24le",
        "pcm_s32le",
        "opus",
        "vorbis",
        "flac",
    }

    # Allowed container formats
    ALLOWED_AUDIO_FORMATS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
    ALLOWED_VIDEO_FORMATS = {".mp4", ".webm", ".avi", ".mov", ".mkv"}

    def __init__(self, max_duration_minutes: int = 30, max_size_mb: int = 100):
        """
        Initialize media validator.

        Args:
            max_duration_minutes: Maximum allowed media duration (SEC-003)
            max_size_mb: Maximum allowed file size in MB (SEC-002)
        """
        self.max_duration_seconds = max_duration_minutes * 60
        self.max_size_bytes = max_size_mb * 1024 * 1024

    def get_file_extension(self, filename: str) -> str:
        """Get lowercase file extension from filename."""
        return Path(filename).suffix.lower()

    def is_audio_file(self, filename: str) -> bool:
        """Check if file extension indicates an audio file."""
        ext = self.get_file_extension(filename)
        return ext in self.ALLOWED_AUDIO_FORMATS

    def is_video_file(self, filename: str) -> bool:
        """Check if file extension indicates a video file."""
        ext = self.get_file_extension(filename)
        return ext in self.ALLOWED_VIDEO_FORMATS

    def is_media_file(self, filename: str) -> bool:
        """Check if file is a supported media file (audio or video)."""
        return self.is_audio_file(filename) or self.is_video_file(filename)

    def validate_file_size(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Validate file size against limit (SEC-002).

        Args:
            file_path: Path to media file

        Returns:
            Tuple of (is_valid, error_message)
        """
        file_size = os.path.getsize(file_path)

        if file_size > self.max_size_bytes:
            size_mb = file_size / (1024 * 1024)
            max_mb = self.max_size_bytes / (1024 * 1024)
            return False, f"File size ({size_mb:.1f} MB) exceeds maximum limit of {max_mb:.0f} MB"

        return True, None

    def run_ffprobe(self, file_path: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Run ffprobe to extract media metadata (FAIL-004).

        Args:
            file_path: Path to media file

        Returns:
            Tuple of (metadata_dict, error_message)
        """
        try:
            # Run ffprobe with JSON output
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return None, f"ffprobe validation failed: {result.stderr}"

            metadata = json.loads(result.stdout)
            return metadata, None

        except subprocess.TimeoutExpired:
            return None, "Media validation timed out. File may be corrupted."
        except json.JSONDecodeError as e:
            return None, f"Failed to parse ffprobe output: {str(e)}"
        except FileNotFoundError:
            return None, "ffprobe not found. Media processing requires ffmpeg installation."
        except Exception as e:
            return None, f"Error validating media file: {str(e)}"

    def extract_metadata(self, ffprobe_data: Dict) -> Dict:
        """
        Extract relevant metadata from ffprobe output.

        Args:
            ffprobe_data: Raw ffprobe JSON output

        Returns:
            Simplified metadata dictionary
        """
        format_info = ffprobe_data.get("format", {})
        streams = ffprobe_data.get("streams", [])

        # Find audio and video streams
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        video_streams = [s for s in streams if s.get("codec_type") == "video"]

        metadata = {
            "duration": float(format_info.get("duration", 0)),
            "size": int(format_info.get("size", 0)),
            "format_name": format_info.get("format_name", "unknown"),
            "bit_rate": int(format_info.get("bit_rate", 0)),
            "has_audio": len(audio_streams) > 0,
            "has_video": len(video_streams) > 0,
            "audio_streams_count": len(audio_streams),
            "video_streams_count": len(video_streams),
        }

        # Add audio stream info if available
        if audio_streams:
            first_audio = audio_streams[0]
            metadata["audio_codec"] = first_audio.get("codec_name", "unknown")
            metadata["audio_channels"] = first_audio.get("channels", 0)
            metadata["audio_sample_rate"] = first_audio.get("sample_rate", "unknown")

        # Add video stream info if available
        if video_streams:
            first_video = video_streams[0]
            metadata["video_codec"] = first_video.get("codec_name", "unknown")
            metadata["width"] = first_video.get("width", 0)
            metadata["height"] = first_video.get("height", 0)

        return metadata

    def validate_media_file(self, file_path: str, filename: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Comprehensive media file validation (REQ-003).

        Validates:
        - File size (SEC-002)
        - File format and codec (EDGE-004)
        - Duration limits (SEC-003)
        - Audio stream presence for videos (EDGE-002)
        - File integrity (EDGE-003)

        Args:
            file_path: Path to media file
            filename: Original filename (for error messages)

        Returns:
            Tuple of (metadata_dict, error_message)
            If validation succeeds, error_message is None
            If validation fails, metadata_dict is None
        """
        # Step 1: Validate file size (SEC-002, EDGE-008)
        is_valid, error = self.validate_file_size(file_path)
        if not is_valid:
            return None, error

        # Step 2: Run ffprobe validation (FAIL-004, EDGE-003)
        ffprobe_data, error = self.run_ffprobe(file_path)
        if error:
            return None, f"Unable to process media file. Format may be unsupported or file may be corrupted. ({error})"

        # Step 3: Extract metadata
        metadata = self.extract_metadata(ffprobe_data)

        # Step 4: Validate duration (SEC-003, EDGE-006)
        if metadata["duration"] > self.max_duration_seconds:
            duration_min = metadata["duration"] / 60
            max_min = self.max_duration_seconds / 60
            return None, f"Media duration ({duration_min:.1f} minutes) exceeds {max_min:.0f}-minute limit"

        # Step 5: Validate audio presence (EDGE-002)
        if not metadata["has_audio"]:
            if self.is_video_file(filename):
                return None, "Video file contains no audio track. Cannot transcribe video without audio."
            else:
                # Audio file with no audio stream (corrupted or wrong format)
                return None, "Audio file contains no audio stream. File may be corrupted."

        # Step 6: Validate audio codec (EDGE-004)
        audio_codec = metadata.get("audio_codec", "unknown")
        if audio_codec not in self.ALLOWED_AUDIO_CODECS:
            return None, f"Unsupported audio codec: {audio_codec}. Supported codecs: {', '.join(sorted(self.ALLOWED_AUDIO_CODECS))}"

        # Step 7: Check for silent audio (EDGE-001)
        # Note: Full silence detection requires processing the audio, which we'll do during transcription
        # Here we just flag extremely low bitrates as potentially silent
        if metadata["bit_rate"] > 0 and metadata["bit_rate"] < 8000:  # Less than 8kbps is suspiciously low
            metadata["potentially_silent"] = True
        else:
            metadata["potentially_silent"] = False

        # Step 8: Multi-track handling (EDGE-007)
        if metadata["audio_streams_count"] > 1:
            metadata["multi_track_warning"] = f"Multiple audio tracks detected ({metadata['audio_streams_count']}), using first track"
        else:
            metadata["multi_track_warning"] = None

        return metadata, None

    def format_duration(self, seconds: float) -> str:
        """Convert seconds to human-readable duration format."""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        if minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def get_validation_summary(self, metadata: Dict) -> str:
        """
        Generate human-readable validation summary.

        Args:
            metadata: Validated metadata dictionary

        Returns:
            Summary string for display
        """
        summary_parts = [
            f"Duration: {self.format_duration(metadata['duration'])}",
            f"Format: {metadata['format_name']}",
            f"Audio Codec: {metadata.get('audio_codec', 'N/A')}",
        ]

        if metadata["has_video"]:
            summary_parts.append(f"Video: {metadata.get('video_codec', 'N/A')}")

        if metadata.get("multi_track_warning"):
            summary_parts.append(f"⚠️ {metadata['multi_track_warning']}")

        return " | ".join(summary_parts)
