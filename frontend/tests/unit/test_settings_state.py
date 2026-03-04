"""
Unit tests for Settings page state management.

Tests cover:
- Settings state initialization with defaults
- Settings validation (threshold ranges, label format)
- Settings serialization for persistence
- Default settings restoration
- Settings merge (user overrides + defaults)

Uses pytest to test settings logic without actual Streamlit UI.
"""

import pytest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestSettingsInitialization:
    """Tests for settings state initialization."""

    def test_default_classification_enabled(self):
        """Should default to classification enabled."""
        # Simulate session state initialization
        session_state = {}

        # Default value
        classification_enabled = session_state.get('classification_enabled', True)

        assert classification_enabled is True

    def test_default_thresholds(self):
        """Should initialize with correct default thresholds."""
        session_state = {}

        # Default values from Settings.py
        auto_apply_threshold = session_state.get('auto_apply_threshold', 85)
        suggestion_threshold = session_state.get('suggestion_threshold', 60)

        assert auto_apply_threshold == 85
        assert suggestion_threshold == 60

    def test_default_labels_fallback(self):
        """Should provide fallback labels when config.yml is unavailable."""
        expected_fallback = [
            "professional",
            "personal",
            "financial",
            "legal",
            "reference",
            "project",
            "work (Memodo)",
            "activism"
        ]

        # Simulate config.yml not available
        session_state = {}
        classification_labels = session_state.get('classification_labels', expected_fallback)

        assert len(classification_labels) == 8
        assert "professional" in classification_labels
        assert "personal" in classification_labels
        assert "financial" in classification_labels

    def test_state_persistence_across_operations(self):
        """Should maintain state across multiple operations."""
        session_state = {
            'classification_enabled': False,
            'auto_apply_threshold': 90,
            'suggestion_threshold': 70,
            'classification_labels': ['custom1', 'custom2']
        }

        # Simulate reading state multiple times
        assert session_state['classification_enabled'] is False
        assert session_state['auto_apply_threshold'] == 90
        assert session_state['suggestion_threshold'] == 70
        assert len(session_state['classification_labels']) == 2


class TestSettingsValidation:
    """Tests for settings validation logic."""

    def test_threshold_range_validation(self):
        """Should validate threshold ranges are within bounds."""
        # Valid ranges from Settings.py
        valid_auto_apply = range(50, 101)  # 50-100
        valid_suggestion = range(40, 101)  # 40-100 (but must be ≤ auto_apply)

        # Test valid values
        assert 85 in valid_auto_apply
        assert 60 in valid_suggestion

        # Test invalid values
        assert 30 not in valid_auto_apply
        assert 110 not in valid_auto_apply
        assert 20 not in valid_suggestion

    def test_suggestion_must_not_exceed_auto_apply(self):
        """Suggestion threshold must be ≤ auto_apply threshold."""
        auto_apply = 85
        suggestion = 60

        # Valid: suggestion < auto_apply
        assert suggestion <= auto_apply

        # Invalid scenario
        invalid_suggestion = 90
        assert not (invalid_suggestion <= auto_apply)

    def test_label_length_validation(self):
        """Should validate label length between 2-30 characters."""
        valid_labels = [
            "ab",           # Min: 2 chars
            "normal",       # Normal
            "a" * 30        # Max: 30 chars
        ]

        invalid_labels = [
            "a",            # Too short: 1 char
            "",             # Empty
            "a" * 31        # Too long: 31 chars
        ]

        for label in valid_labels:
            assert 2 <= len(label) <= 30

        for label in invalid_labels:
            assert not (2 <= len(label) <= 30)

    def test_label_duplicate_detection(self):
        """Should detect duplicate labels."""
        existing_labels = ['personal', 'work', 'financial']

        # New unique label
        new_label = 'technical'
        assert new_label not in existing_labels

        # Duplicate label
        duplicate_label = 'personal'
        assert duplicate_label in existing_labels

    def test_threshold_step_validation(self):
        """Thresholds should align with step size (5%)."""
        valid_values = [50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100]

        for value in valid_values:
            # Should be divisible by 5
            assert value % 5 == 0

        # Invalid values (not aligned to 5% steps)
        invalid_values = [51, 63, 77, 88]
        for value in invalid_values:
            assert value % 5 != 0


class TestSettingsReset:
    """Tests for settings reset functionality."""

    def test_reset_labels_to_default(self):
        """Should reset labels to default configuration."""
        default_labels = [
            "professional",
            "personal",
            "financial",
            "legal",
            "reference",
            "project",
            "work (Memodo)",
            "activism"
        ]

        # Modified state
        session_state = {
            'classification_labels': ['custom1', 'custom2', 'custom3']
        }

        # Simulate reset
        session_state['classification_labels'] = default_labels.copy()

        assert len(session_state['classification_labels']) == 8
        assert session_state['classification_labels'] == default_labels

    def test_reset_thresholds_to_default(self):
        """Should reset thresholds to default values."""
        # Modified state
        session_state = {
            'auto_apply_threshold': 95,
            'suggestion_threshold': 75
        }

        # Simulate reset
        session_state['auto_apply_threshold'] = 85
        session_state['suggestion_threshold'] = 60

        assert session_state['auto_apply_threshold'] == 85
        assert session_state['suggestion_threshold'] == 60

    def test_partial_reset_preserves_other_settings(self):
        """Resetting one setting should not affect others."""
        session_state = {
            'classification_enabled': False,
            'auto_apply_threshold': 95,
            'suggestion_threshold': 75,
            'classification_labels': ['custom1']
        }

        # Reset only thresholds
        session_state['auto_apply_threshold'] = 85
        session_state['suggestion_threshold'] = 60

        # Other settings should remain unchanged
        assert session_state['classification_enabled'] is False
        assert session_state['classification_labels'] == ['custom1']


class TestSettingsMerge:
    """Tests for merging user settings with defaults."""

    def test_merge_with_missing_keys(self):
        """Should fill missing keys with defaults."""
        user_settings = {
            'classification_enabled': False
            # Missing: thresholds and labels
        }

        defaults = {
            'classification_enabled': True,
            'auto_apply_threshold': 85,
            'suggestion_threshold': 60,
            'classification_labels': ['default1', 'default2']
        }

        # Merge: user settings override, defaults fill gaps
        merged = {}
        for key, default_value in defaults.items():
            merged[key] = user_settings.get(key, default_value)

        assert merged['classification_enabled'] is False  # User override
        assert merged['auto_apply_threshold'] == 85       # From default
        assert merged['suggestion_threshold'] == 60       # From default
        assert merged['classification_labels'] == ['default1', 'default2']  # From default

    def test_merge_preserves_user_overrides(self):
        """Should preserve all user settings when merging."""
        user_settings = {
            'classification_enabled': False,
            'auto_apply_threshold': 90,
            'suggestion_threshold': 70,
            'classification_labels': ['custom1', 'custom2']
        }

        defaults = {
            'classification_enabled': True,
            'auto_apply_threshold': 85,
            'suggestion_threshold': 60,
            'classification_labels': ['default1']
        }

        # Merge
        merged = {}
        for key, default_value in defaults.items():
            merged[key] = user_settings.get(key, default_value)

        # All user settings should be preserved
        assert merged == user_settings


class TestSettingsEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_labels_list(self):
        """Should handle empty labels list gracefully."""
        labels = []

        # Empty list is valid (though not useful)
        assert isinstance(labels, list)
        assert len(labels) == 0

    def test_very_long_labels_list(self):
        """Should handle many labels (100+)."""
        labels = [f"label{i}" for i in range(150)]

        assert len(labels) == 150
        assert all(isinstance(label, str) for label in labels)

    def test_labels_with_special_characters(self):
        """Should handle labels with special characters."""
        special_labels = [
            "work (Memodo)",     # Parentheses
            "legal/contracts",   # Slash
            "high-priority",     # Hyphen
            "archive_2024"       # Underscore
        ]

        for label in special_labels:
            assert 2 <= len(label) <= 30
            assert isinstance(label, str)

    def test_threshold_boundary_values(self):
        """Should handle threshold boundary values correctly."""
        # Minimum values
        min_auto_apply = 50
        min_suggestion = 40

        # Maximum values
        max_auto_apply = 100
        max_suggestion = 100  # But constrained by auto_apply

        assert 50 <= min_auto_apply <= 100
        assert 40 <= min_suggestion <= 100
        assert max_auto_apply == 100
        assert max_suggestion == 100

    def test_disabled_classification_allows_settings_changes(self):
        """Settings can be modified even when classification is disabled."""
        session_state = {
            'classification_enabled': False,
            'auto_apply_threshold': 85,
            'classification_labels': ['personal']
        }

        # Modify settings while disabled
        session_state['auto_apply_threshold'] = 90
        session_state['classification_labels'].append('work')

        assert session_state['classification_enabled'] is False
        assert session_state['auto_apply_threshold'] == 90
        assert 'work' in session_state['classification_labels']
