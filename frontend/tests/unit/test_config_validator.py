"""
Unit tests for ConfigValidator class (REQ-005).

Tests cover:
- Valid configuration validation
- Missing required fields detection
- Invalid YAML handling
- graph.approximate validation (critical setting)
- ValidationResult structure and methods

Uses temporary files to test YAML parsing without depending on actual config files.
"""

import pytest
import tempfile
import os
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.config_validator import ConfigValidator, ValidationResult


class TestValidationResult:
    """Tests for ValidationResult class."""

    def test_valid_result_is_truthy(self):
        """Valid result should be truthy when cast to bool."""
        result = ValidationResult(is_valid=True, errors=[], warnings=[])
        assert bool(result) is True

    def test_invalid_result_is_falsy(self):
        """Invalid result should be falsy when cast to bool."""
        result = ValidationResult(is_valid=False, errors=["Error"], warnings=[])
        assert bool(result) is False

    def test_get_message_for_valid_config(self):
        """Valid config message should contain success indicator."""
        result = ValidationResult(is_valid=True, errors=[], warnings=[])
        message = result.get_message()
        assert "valid" in message.lower() or "✅" in message

    def test_get_message_for_invalid_config(self):
        """Invalid config message should contain error details."""
        result = ValidationResult(is_valid=False, errors=["Missing field"], warnings=[])
        message = result.get_message()
        assert "Missing field" in message
        assert "failed" in message.lower() or "❌" in message

    def test_get_message_includes_warnings(self):
        """Message should include warnings when present."""
        result = ValidationResult(is_valid=True, errors=[], warnings=["Consider setting X"])
        message = result.get_message()
        assert "Consider setting X" in message

    def test_errors_and_warnings_are_lists(self):
        """Errors and warnings should be accessible as lists."""
        result = ValidationResult(
            is_valid=False,
            errors=["Error 1", "Error 2"],
            warnings=["Warning 1"]
        )
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)
        assert len(result.errors) == 2
        assert len(result.warnings) == 1


class TestConfigValidatorLoadConfig:
    """Tests for configuration loading."""

    def test_load_valid_yaml_file(self):
        """Valid YAML file should load successfully."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
writable: true
embeddings:
  path: model/path
  content: true
graph:
  approximate: false
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            result = validator.load_config()

        os.unlink(f.name)
        assert result is True
        assert validator.config is not None

    def test_load_nonexistent_file_returns_false(self):
        """Nonexistent file should return False."""
        validator = ConfigValidator(config_path="/nonexistent/path/config.yml")
        result = validator.load_config()
        assert result is False

    def test_load_invalid_yaml_returns_false(self):
        """Invalid YAML should return False."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            # Use a tab character which causes YAML parse error
            f.write("key:\n\t- invalid tab indentation")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            result = validator.load_config()

        os.unlink(f.name)
        assert result is False


class TestConfigValidatorValidate:
    """Tests for configuration validation."""

    def test_valid_config_passes_validation(self):
        """Fully valid config should pass validation."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
writable: true
embeddings:
  path: BAAI/bge-large-en-v1.5
  content: true
graph:
  approximate: false
  limit: 15
  minscore: 0.1
path: /data/index
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            result = validator.validate()

        os.unlink(f.name)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_missing_writable_is_error(self):
        """Missing writable setting should be an error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
embeddings:
  path: model/path
graph:
  approximate: false
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            result = validator.validate()

        os.unlink(f.name)
        assert result.is_valid is False
        assert any("writable" in e.lower() for e in result.errors)

    def test_missing_embeddings_is_error(self):
        """Missing embeddings configuration should be an error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
writable: true
graph:
  approximate: false
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            result = validator.validate()

        os.unlink(f.name)
        assert result.is_valid is False
        assert any("embeddings" in e.lower() for e in result.errors)

    def test_missing_embeddings_path_is_error(self):
        """Missing embeddings.path should be an error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
writable: true
embeddings:
  content: true
graph:
  approximate: false
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            result = validator.validate()

        os.unlink(f.name)
        assert result.is_valid is False
        assert any("path" in e.lower() for e in result.errors)


class TestConfigValidatorGraphApproximate:
    """Tests for graph.approximate validation (CRITICAL)."""

    def test_graph_approximate_false_is_valid(self):
        """graph.approximate: false should pass validation."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
writable: true
embeddings:
  path: model/path
graph:
  approximate: false
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            result = validator.validate()

        os.unlink(f.name)
        assert result.is_valid is True

    def test_graph_approximate_true_is_error(self):
        """graph.approximate: true should be a CRITICAL error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
writable: true
embeddings:
  path: model/path
graph:
  approximate: true
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            result = validator.validate()

        os.unlink(f.name)
        assert result.is_valid is False
        # Error should mention "approximate" and "CRITICAL"
        assert any("approximate" in e.lower() for e in result.errors)
        assert any("critical" in e.lower() for e in result.errors)

    def test_missing_graph_section_is_error(self):
        """Missing graph section entirely should be an error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
writable: true
embeddings:
  path: model/path
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            result = validator.validate()

        os.unlink(f.name)
        assert result.is_valid is False
        assert any("graph" in e.lower() for e in result.errors)

    def test_missing_graph_approximate_setting_is_error(self):
        """Missing graph.approximate setting should be an error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
writable: true
embeddings:
  path: model/path
graph:
  limit: 15
  minscore: 0.1
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            result = validator.validate()

        os.unlink(f.name)
        assert result.is_valid is False
        assert any("approximate" in e.lower() for e in result.errors)


class TestConfigValidatorWarnings:
    """Tests for configuration warnings (non-critical issues)."""

    def test_missing_embeddings_content_is_warning(self):
        """Missing embeddings.content should be a warning, not error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
writable: true
embeddings:
  path: model/path
graph:
  approximate: false
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            result = validator.validate()

        os.unlink(f.name)
        # Should still be valid, but have warning
        assert result.is_valid is True
        assert any("content" in w.lower() for w in result.warnings)

    def test_missing_graph_limit_is_warning(self):
        """Missing graph.limit should be a warning."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
writable: true
embeddings:
  path: model/path
  content: true
graph:
  approximate: false
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            result = validator.validate()

        os.unlink(f.name)
        assert result.is_valid is True
        assert any("limit" in w.lower() for w in result.warnings)

    def test_missing_graph_minscore_is_warning(self):
        """Missing graph.minscore should be a warning."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
writable: true
embeddings:
  path: model/path
  content: true
graph:
  approximate: false
  limit: 15
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            result = validator.validate()

        os.unlink(f.name)
        assert result.is_valid is True
        assert any("minscore" in w.lower() for w in result.warnings)

    def test_missing_path_is_warning(self):
        """Missing path setting should be a warning."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
writable: true
embeddings:
  path: model/path
  content: true
graph:
  approximate: false
  limit: 15
  minscore: 0.1
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            result = validator.validate()

        os.unlink(f.name)
        # All critical settings present but path missing = valid with warning
        assert result.is_valid is True
        assert any("path" in w.lower() for w in result.warnings)


class TestConfigValidatorFileNotLoaded:
    """Tests for validation when config not pre-loaded."""

    def test_validate_loads_config_automatically(self):
        """validate() should load config if not already loaded."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
writable: true
embeddings:
  path: model/path
graph:
  approximate: false
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            # Don't call load_config explicitly
            assert validator.config is None
            result = validator.validate()

        os.unlink(f.name)
        # Config should now be loaded
        assert validator.config is not None

    def test_validate_with_load_failure_returns_error(self):
        """validate() with failed config load should return error."""
        validator = ConfigValidator(config_path="/nonexistent/config.yml")
        result = validator.validate()

        assert result.is_valid is False
        assert any("load" in e.lower() or "failed" in e.lower() for e in result.errors)


class TestConfigValidatorGetGraphStatus:
    """Tests for get_graph_status() method."""

    def test_graph_status_correct_when_approximate_false(self):
        """get_graph_status should return correct status when approximate=false."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
graph:
  approximate: false
  limit: 15
  minscore: 0.1
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            status = validator.get_graph_status()

        os.unlink(f.name)
        assert status["configured"] is True
        assert status["approximate"] is False
        assert status["status"] == "correct"

    def test_graph_status_incorrect_when_approximate_true(self):
        """get_graph_status should return incorrect status when approximate=true."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
graph:
  approximate: true
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            status = validator.get_graph_status()

        os.unlink(f.name)
        assert status["configured"] is True
        assert status["approximate"] is True
        assert status["status"] == "incorrect"

    def test_graph_status_missing_when_no_graph_section(self):
        """get_graph_status should return missing status when no graph config."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
embeddings:
  path: model/path
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            status = validator.get_graph_status()

        os.unlink(f.name)
        assert status["configured"] is False
        assert status["status"] == "missing"

    def test_graph_status_includes_limit_and_minscore(self):
        """get_graph_status should include limit and minscore values."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
graph:
  approximate: false
  limit: 20
  minscore: 0.2
""")
            f.flush()
            validator = ConfigValidator(config_path=f.name)
            status = validator.get_graph_status()

        os.unlink(f.name)
        assert status["limit"] == 20
        assert status["minscore"] == 0.2


class TestConfigValidatorSuggestGraphConfig:
    """Tests for suggest_graph_config() method."""

    def test_suggestion_includes_approximate_false(self):
        """Suggested config should include approximate: false."""
        validator = ConfigValidator()
        suggestion = validator.suggest_graph_config()

        assert "approximate" in suggestion.lower()
        assert "false" in suggestion.lower()

    def test_suggestion_includes_limit(self):
        """Suggested config should include limit setting."""
        validator = ConfigValidator()
        suggestion = validator.suggest_graph_config()

        assert "limit" in suggestion.lower()

    def test_suggestion_includes_minscore(self):
        """Suggested config should include minscore setting."""
        validator = ConfigValidator()
        suggestion = validator.suggest_graph_config()

        assert "minscore" in suggestion.lower()

    def test_suggestion_is_valid_yaml(self):
        """Suggested config should be valid YAML."""
        import yaml
        validator = ConfigValidator()
        suggestion = validator.suggest_graph_config()

        # Should parse without error
        parsed = yaml.safe_load(suggestion)
        assert "graph" in parsed
        assert parsed["graph"]["approximate"] is False
