"""
Unit tests for DocumentProcessor.extract_text_from_audio() and extract_text_from_video() (REQ-009).

Tests audio/video transcription covering:
- WAV/MP3/M4A transcription
- Video transcription (audio extraction + transcription)
- Very long media (duration limits)
- Corrupt files (graceful error)
- Silent audio (no speech detected)
- Missing dependencies (moviepy, etc.)
"""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add frontend to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.document_processor import DocumentProcessor


class TestExtractTextFromAudio:
    """Tests for DocumentProcessor.extract_text_from_audio()"""

    @pytest.fixture
    def processor(self):
        """Create DocumentProcessor instance."""
        return DocumentProcessor()

    @pytest.fixture
    def fixtures_dir(self):
        """Path to test fixtures."""
        return Path(__file__).parent.parent / "fixtures"

    # -------------------------------------------------------------------------
    # Basic Functionality Tests (with mocked API)
    # -------------------------------------------------------------------------

    def test_valid_wav_transcription(self, processor, fixtures_dir):
        """Valid WAV file should transcribe successfully."""
        wav_path = fixtures_dir / "sample.wav"
        if not wav_path.exists():
            pytest.skip("sample.wav fixture not available")

        # Mock the validation and API call
        mock_metadata = {
            "duration": 5.0,
            "format": "wav",
            "sample_rate": 44100
        }

        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (mock_metadata, None)
            mock_validator_class.return_value = mock_validator

            with patch.object(processor, '_transcribe_via_api', return_value=("Hello world transcription", None)):
                text, error, metadata = processor.extract_text_from_audio(
                    str(wav_path), "sample.wav"
                )

        assert error is None, f"Unexpected error: {error}"
        assert text, "Should return transcribed text"
        assert "Hello world" in text

    def test_valid_mp3_transcription(self, processor, fixtures_dir):
        """Valid MP3 file should transcribe successfully."""
        # Use the large.mp3 fixture if available (just testing the path, not actual transcription)
        mp3_path = fixtures_dir / "large.mp3"
        if not mp3_path.exists():
            pytest.skip("large.mp3 fixture not available")

        mock_metadata = {"duration": 300.0, "format": "mp3"}

        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (mock_metadata, None)
            mock_validator_class.return_value = mock_validator

            with patch.object(processor, '_transcribe_via_api', return_value=("MP3 transcription text", None)):
                text, error, metadata = processor.extract_text_from_audio(
                    str(mp3_path), "large.mp3"
                )

        assert error is None
        assert "MP3 transcription" in text

    def test_valid_m4a_transcription(self, processor, fixtures_dir):
        """Valid M4A file should transcribe successfully."""
        m4a_path = fixtures_dir / "sample.m4a"
        if not m4a_path.exists():
            pytest.skip("sample.m4a fixture not available")

        mock_metadata = {"duration": 10.0, "format": "m4a"}

        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (mock_metadata, None)
            mock_validator_class.return_value = mock_validator

            with patch.object(processor, '_transcribe_via_api', return_value=("M4A audio content", None)):
                text, error, metadata = processor.extract_text_from_audio(
                    str(m4a_path), "sample.m4a"
                )

        assert error is None
        assert text

    def test_metadata_includes_transcription_info(self, processor, fixtures_dir):
        """Metadata should include transcription model info."""
        wav_path = fixtures_dir / "sample.wav"
        if not wav_path.exists():
            pytest.skip("sample.wav fixture not available")

        mock_metadata = {"duration": 5.0, "format": "wav"}

        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (mock_metadata, None)
            mock_validator_class.return_value = mock_validator

            with patch.object(processor, '_transcribe_via_api', return_value=("Transcribed text", None)):
                text, error, metadata = processor.extract_text_from_audio(
                    str(wav_path), "sample.wav"
                )

        assert error is None
        assert metadata is not None
        assert "transcription_model" in metadata
        assert "media_type" in metadata
        assert metadata["media_type"] == "audio"

    # -------------------------------------------------------------------------
    # Error Handling Tests
    # -------------------------------------------------------------------------

    def test_validation_failure_returns_error(self, processor):
        """Validation failure should return error."""
        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (None, "File too large")
            mock_validator_class.return_value = mock_validator

            text, error, metadata = processor.extract_text_from_audio(
                "/path/to/file.wav", "file.wav"
            )

        assert text == ""
        assert error is not None
        assert "File too large" in error

    def test_transcription_api_failure_returns_error(self, processor, fixtures_dir):
        """API transcription failure should return error."""
        wav_path = fixtures_dir / "sample.wav"
        if not wav_path.exists():
            pytest.skip("sample.wav fixture not available")

        mock_metadata = {"duration": 5.0, "format": "wav"}

        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (mock_metadata, None)
            mock_validator_class.return_value = mock_validator

            with patch.object(processor, '_transcribe_via_api', return_value=("", "Transcription service unavailable")):
                text, error, metadata = processor.extract_text_from_audio(
                    str(wav_path), "sample.wav"
                )

        assert text == ""
        assert error is not None
        assert "unavailable" in error.lower() or "Transcription" in error

    def test_silent_audio_returns_error(self, processor, fixtures_dir):
        """Silent audio (no speech) should return appropriate error."""
        wav_path = fixtures_dir / "sample.wav"
        if not wav_path.exists():
            pytest.skip("sample.wav fixture not available")

        mock_metadata = {"duration": 5.0, "format": "wav"}

        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (mock_metadata, None)
            mock_validator_class.return_value = mock_validator

            # Empty transcription indicates silence
            with patch.object(processor, '_transcribe_via_api', return_value=("", None)):
                text, error, metadata = processor.extract_text_from_audio(
                    str(wav_path), "sample.wav"
                )

        assert text == ""
        assert error is not None
        assert "speech" in error.lower() or "silent" in error.lower()

    def test_exception_handling(self, processor):
        """Exception during processing should return error."""
        with patch('utils.media_validator.MediaValidator', side_effect=Exception("Unexpected error")):
            text, error, metadata = processor.extract_text_from_audio(
                "/path/to/file.wav", "file.wav"
            )

        assert text == ""
        assert error is not None

    # -------------------------------------------------------------------------
    # Return Type Validation Tests
    # -------------------------------------------------------------------------

    def test_returns_tuple_of_text_error_metadata(self, processor, fixtures_dir):
        """Should return (text, error, metadata) tuple."""
        wav_path = fixtures_dir / "sample.wav"
        if not wav_path.exists():
            pytest.skip("sample.wav fixture not available")

        mock_metadata = {"duration": 5.0, "format": "wav"}

        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (mock_metadata, None)
            mock_validator_class.return_value = mock_validator

            with patch.object(processor, '_transcribe_via_api', return_value=("Text", None)):
                result = processor.extract_text_from_audio(str(wav_path), "sample.wav")

        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_error_case_returns_empty_string_and_none_metadata(self, processor):
        """Error case should return ('', error, None)."""
        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (None, "Invalid file")
            mock_validator_class.return_value = mock_validator

            text, error, metadata = processor.extract_text_from_audio("/path/to/file.wav", "file.wav")

        assert text == ""
        assert error is not None
        assert metadata is None


class TestExtractTextFromVideo:
    """Tests for DocumentProcessor.extract_text_from_video()"""

    @pytest.fixture
    def processor(self):
        return DocumentProcessor()

    @pytest.fixture
    def fixtures_dir(self):
        return Path(__file__).parent.parent / "fixtures"

    # -------------------------------------------------------------------------
    # Basic Functionality Tests (with mocked components)
    # -------------------------------------------------------------------------

    def test_valid_video_extracts_audio_and_transcribes(self, processor, fixtures_dir):
        """Valid video should extract audio and transcribe."""
        video_path = fixtures_dir / "short.mp4"
        if not video_path.exists():
            pytest.skip("short.mp4 fixture not available")

        mock_metadata = {"duration": 10.0, "format": "mp4", "has_audio": True}

        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (mock_metadata, None)
            mock_validator_class.return_value = mock_validator

            # Mock the VideoFileClip
            mock_audio = MagicMock()
            mock_video = MagicMock()
            mock_video.audio = mock_audio

            with patch('moviepy.editor.VideoFileClip', return_value=mock_video):
                with patch.object(processor, '_transcribe_via_api', return_value=("Video transcription", None)):
                    text, error, metadata = processor.extract_text_from_video(
                        str(video_path), "short.mp4"
                    )

        assert error is None
        assert text
        assert "Video transcription" in text

    def test_video_metadata_includes_media_type(self, processor, fixtures_dir):
        """Video metadata should indicate video media type."""
        video_path = fixtures_dir / "short.mp4"
        if not video_path.exists():
            pytest.skip("short.mp4 fixture not available")

        mock_metadata = {"duration": 10.0, "format": "mp4"}

        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (mock_metadata, None)
            mock_validator_class.return_value = mock_validator

            mock_video = MagicMock()
            mock_video.audio = MagicMock()

            with patch('moviepy.editor.VideoFileClip', return_value=mock_video):
                with patch.object(processor, '_transcribe_via_api', return_value=("Text", None)):
                    text, error, metadata = processor.extract_text_from_video(
                        str(video_path), "short.mp4"
                    )

        assert error is None
        assert metadata is not None
        assert metadata.get("media_type") == "video"

    # -------------------------------------------------------------------------
    # Error Handling Tests
    # -------------------------------------------------------------------------

    def test_media_processing_not_available(self, processor):
        """When moviepy not available, should return appropriate error."""
        processor.media_processing_available = False

        text, error, metadata = processor.extract_text_from_video("/path/to/video.mp4", "video.mp4")

        assert text == ""
        assert error is not None
        assert "moviepy" in error.lower() or "media processing" in error.lower()

    def test_validation_failure_returns_error(self, processor):
        """Video validation failure should return error."""
        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (None, "Unsupported codec")
            mock_validator_class.return_value = mock_validator

            text, error, metadata = processor.extract_text_from_video("/path/to/video.mp4", "video.mp4")

        assert text == ""
        assert error is not None
        assert "codec" in error.lower() or "Unsupported" in error

    def test_audio_extraction_failure_returns_error(self, processor, fixtures_dir):
        """Failure to extract audio should return error."""
        video_path = fixtures_dir / "short.mp4"
        if not video_path.exists():
            pytest.skip("short.mp4 fixture not available")

        mock_metadata = {"duration": 10.0, "format": "mp4"}

        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (mock_metadata, None)
            mock_validator_class.return_value = mock_validator

            # Mock VideoFileClip to raise an exception when instantiated
            with patch('utils.document_processor.VideoFileClip', side_effect=Exception("Cannot read video")):
                text, error, metadata = processor.extract_text_from_video(
                    str(video_path), "short.mp4"
                )

        assert text == ""
        assert error is not None
        # Error should mention audio extraction failure or be a general error
        assert "audio" in error.lower() or "video" in error.lower() or "extract" in error.lower() or "failed" in error.lower()

    # -------------------------------------------------------------------------
    # Return Type Validation Tests
    # -------------------------------------------------------------------------

    def test_returns_tuple_of_text_error_metadata(self, processor, fixtures_dir):
        """Should return (text, error, metadata) tuple."""
        video_path = fixtures_dir / "short.mp4"
        if not video_path.exists():
            pytest.skip("short.mp4 fixture not available")

        mock_metadata = {"duration": 10.0, "format": "mp4"}

        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (mock_metadata, None)
            mock_validator_class.return_value = mock_validator

            mock_video = MagicMock()
            mock_video.audio = MagicMock()

            with patch('moviepy.editor.VideoFileClip', return_value=mock_video):
                with patch.object(processor, '_transcribe_via_api', return_value=("Text", None)):
                    result = processor.extract_text_from_video(str(video_path), "short.mp4")

        assert isinstance(result, tuple)
        assert len(result) == 3


class TestAudioVideoEdgeCases:
    """Tests for edge cases in audio/video processing."""

    @pytest.fixture
    def processor(self):
        return DocumentProcessor()

    @pytest.fixture
    def fixtures_dir(self):
        return Path(__file__).parent.parent / "fixtures"

    def test_very_long_audio_handled(self, processor, fixtures_dir):
        """Very long audio should be validated against duration limits."""
        # large.mp3 is about 15 minutes
        mp3_path = fixtures_dir / "large.mp3"
        if not mp3_path.exists():
            pytest.skip("large.mp3 fixture not available")

        # Mock validation to return duration error
        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (None, "Duration exceeds maximum of 30 minutes")
            mock_validator_class.return_value = mock_validator

            text, error, metadata = processor.extract_text_from_audio(
                str(mp3_path), "large.mp3"
            )

        assert text == ""
        assert error is not None
        assert "duration" in error.lower() or "maximum" in error.lower()

    def test_corrupt_audio_returns_error(self, processor):
        """Corrupt audio file should return error."""
        # Create a temp file with invalid content
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"Not a valid WAV file")
            temp_path = f.name

        try:
            with patch('utils.media_validator.MediaValidator') as mock_validator_class:
                mock_validator = MagicMock()
                mock_validator.validate_media_file.return_value = (None, "Invalid WAV header")
                mock_validator_class.return_value = mock_validator

                text, error, metadata = processor.extract_text_from_audio(
                    temp_path, "corrupt.wav"
                )

            assert text == ""
            assert error is not None
        finally:
            os.unlink(temp_path)

    def test_corrupt_video_returns_error(self, processor):
        """Corrupt video file should return error."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"Not a valid MP4 file")
            temp_path = f.name

        try:
            with patch('utils.media_validator.MediaValidator') as mock_validator_class:
                mock_validator = MagicMock()
                mock_validator.validate_media_file.return_value = (None, "Invalid video format")
                mock_validator_class.return_value = mock_validator

                text, error, metadata = processor.extract_text_from_video(
                    temp_path, "corrupt.mp4"
                )

            assert text == ""
            assert error is not None
        finally:
            os.unlink(temp_path)

    def test_progress_callback_called(self, processor, fixtures_dir):
        """Progress callback should be called during processing."""
        wav_path = fixtures_dir / "sample.wav"
        if not wav_path.exists():
            pytest.skip("sample.wav fixture not available")

        progress_calls = []

        def track_progress(progress, message):
            progress_calls.append((progress, message))

        mock_metadata = {"duration": 5.0, "format": "wav"}

        with patch('utils.media_validator.MediaValidator') as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate_media_file.return_value = (mock_metadata, None)
            mock_validator_class.return_value = mock_validator

            with patch.object(processor, '_transcribe_via_api', return_value=("Text", None)):
                text, error, metadata = processor.extract_text_from_audio(
                    str(wav_path), "sample.wav", progress_callback=track_progress
                )

        assert error is None
        assert len(progress_calls) > 0, "Progress callback should be called"
