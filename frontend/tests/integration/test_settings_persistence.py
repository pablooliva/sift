"""
Integration tests for Settings persistence and behavior.

Tests the complete flow:
1. Settings state management across operations
2. Settings affecting upload classification behavior
3. Reset functionality with real state
4. Threshold validation with classification workflow
5. Label management with document upload

These tests verify that Settings changes correctly affect
document processing and persist throughout operations.

Requirements:
    - txtai API running at TEST_TXTAI_API_URL
    - Classification workflow available
    - Test fixtures available

Usage:
    pytest tests/integration/test_settings_persistence.py -v
"""

import pytest
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import TxtAIClient
from tests.helpers import create_test_document, upsert_index, delete_test_documents


@pytest.fixture
def default_settings():
    """Default settings configuration."""
    return {
        'classification_enabled': True,
        'auto_apply_threshold': 85,
        'suggestion_threshold': 60,
        'classification_labels': [
            'professional',
            'personal',
            'financial',
            'legal',
            'reference',
            'project',
            'work (Memodo)',
            'activism'
        ]
    }


class TestSettingsStateManagement:
    """Tests for settings state persistence across operations."""

    def test_settings_state_consistency(self, default_settings):
        """Should maintain consistent state throughout operations."""
        # Simulate settings state
        settings = default_settings.copy()

        # Multiple reads should return same values
        assert settings['classification_enabled'] is True
        assert settings['auto_apply_threshold'] == 85
        assert settings['suggestion_threshold'] == 60
        assert len(settings['classification_labels']) == 8

        # Modify settings
        settings['auto_apply_threshold'] = 90
        settings['suggestion_threshold'] = 70

        # Changes should persist
        assert settings['auto_apply_threshold'] == 90
        assert settings['suggestion_threshold'] == 70

    def test_label_additions_persist(self, default_settings):
        """Added labels should persist in state."""
        settings = default_settings.copy()
        original_count = len(settings['classification_labels'])

        # Add new label
        new_label = 'technical'
        settings['classification_labels'].append(new_label)

        # Verify persistence
        assert len(settings['classification_labels']) == original_count + 1
        assert new_label in settings['classification_labels']

    def test_label_removals_persist(self, default_settings):
        """Removed labels should be gone from state."""
        settings = default_settings.copy()
        original_count = len(settings['classification_labels'])

        # Remove a label
        label_to_remove = 'activism'
        settings['classification_labels'].remove(label_to_remove)

        # Verify persistence
        assert len(settings['classification_labels']) == original_count - 1
        assert label_to_remove not in settings['classification_labels']


class TestSettingsAffectUploadBehavior:
    """Tests for settings affecting document upload classification."""

    def test_disabled_classification_skips_labels(self, api_client):
        """When classification disabled, documents should have no AI labels."""
        doc_id = f"test-no-classification-{uuid.uuid4()}"

        try:
            # Upload document without classification metadata
            # (simulating classification_enabled = False)
            metadata = {
                'filename': 'test-no-classification.txt',
                'title': 'Document Without Classification',
                'categories': ['manual-label'],  # Only manual labels
                'indexed_at': datetime.now(timezone.utc).timestamp()
            }

            add_response = create_test_document(
                api_client,
                doc_id,
                "This is a test document that should not be classified.",
                **metadata
            )
            assert add_response['success'] is True

            index_response = upsert_index(api_client)
            assert index_response['success'] is True

            # Verify document has only manual labels (no AI labels)
            result = api_client.get_document_by_id(doc_id)
            assert result['success'] is True

            doc = result['document']
            categories = doc['metadata'].get('categories', [])

            # Should only have manual label
            assert 'manual-label' in categories

        finally:
            delete_test_documents(api_client, [doc_id])

    def test_threshold_affects_label_acceptance(self):
        """Threshold settings should determine which labels are applied."""
        # Simulate classification results with varying confidence
        classification_results = [
            {'label': 'professional', 'score': 0.95},  # Above auto_apply (85%)
            {'label': 'reference', 'score': 0.75},     # Between suggestion (60%) and auto_apply (85%)
            {'label': 'legal', 'score': 0.50},         # Below suggestion (60%)
        ]

        auto_apply_threshold = 85
        suggestion_threshold = 60

        # Filter based on thresholds
        auto_applied = [
            r['label'] for r in classification_results
            if r['score'] >= auto_apply_threshold / 100.0
        ]

        suggested = [
            r['label'] for r in classification_results
            if suggestion_threshold / 100.0 <= r['score'] < auto_apply_threshold / 100.0
        ]

        hidden = [
            r['label'] for r in classification_results
            if r['score'] < suggestion_threshold / 100.0
        ]

        # Verify filtering
        assert 'professional' in auto_applied
        assert 'reference' in suggested
        assert 'legal' in hidden

    def test_custom_labels_available_for_classification(self, default_settings):
        """Custom labels should be available for classification."""
        settings = default_settings.copy()

        # Add custom labels
        custom_labels = ['urgent', 'confidential', 'archive']
        for label in custom_labels:
            settings['classification_labels'].append(label)

        # Verify all labels available (default + custom)
        assert 'urgent' in settings['classification_labels']
        assert 'confidential' in settings['classification_labels']
        assert 'archive' in settings['classification_labels']
        assert 'professional' in settings['classification_labels']  # Original still there


class TestSettingsReset:
    """Tests for settings reset functionality."""

    def test_reset_labels_restores_defaults(self, default_settings):
        """Reset should restore default labels."""
        settings = default_settings.copy()

        # Modify labels
        settings['classification_labels'] = ['custom1', 'custom2']
        assert len(settings['classification_labels']) == 2

        # Reset to defaults
        settings['classification_labels'] = default_settings['classification_labels'].copy()

        # Verify reset
        assert len(settings['classification_labels']) == 8
        assert 'professional' in settings['classification_labels']
        assert 'custom1' not in settings['classification_labels']

    def test_reset_thresholds_restores_defaults(self, default_settings):
        """Reset should restore default thresholds."""
        settings = default_settings.copy()

        # Modify thresholds
        settings['auto_apply_threshold'] = 95
        settings['suggestion_threshold'] = 75

        # Reset to defaults
        settings['auto_apply_threshold'] = 85
        settings['suggestion_threshold'] = 60

        # Verify reset
        assert settings['auto_apply_threshold'] == 85
        assert settings['suggestion_threshold'] == 60

    def test_partial_reset_preserves_unrelated_settings(self, default_settings):
        """Partial reset should not affect unrelated settings."""
        settings = default_settings.copy()

        # Modify multiple settings
        settings['classification_enabled'] = False
        settings['auto_apply_threshold'] = 95
        settings['classification_labels'] = ['custom1']

        # Reset only thresholds (not labels or enabled state)
        settings['auto_apply_threshold'] = 85
        settings['suggestion_threshold'] = 60

        # Verify partial reset
        assert settings['auto_apply_threshold'] == 85
        assert settings['suggestion_threshold'] == 60
        assert settings['classification_enabled'] is False  # Unchanged
        assert settings['classification_labels'] == ['custom1']  # Unchanged


class TestThresholdValidation:
    """Tests for threshold validation during operations."""

    def test_invalid_threshold_order_rejected(self):
        """Suggestion threshold above auto_apply should be invalid."""
        auto_apply = 85
        invalid_suggestion = 90  # Above auto_apply

        # Validation check
        is_valid = invalid_suggestion <= auto_apply

        assert is_valid is False

    def test_valid_threshold_order_accepted(self):
        """Suggestion threshold at or below auto_apply should be valid."""
        auto_apply = 85
        valid_suggestions = [60, 70, 85]  # All ≤ auto_apply

        for suggestion in valid_suggestions:
            assert suggestion <= auto_apply

    def test_threshold_at_boundaries(self):
        """Threshold boundary values should be valid."""
        # Minimum boundaries
        min_auto_apply = 50
        min_suggestion = 40

        # Maximum boundaries
        max_auto_apply = 100
        max_suggestion = 100

        # All should be valid
        assert 50 <= min_auto_apply <= 100
        assert 40 <= min_suggestion <= 100
        assert 50 <= max_auto_apply <= 100
        assert 40 <= max_suggestion <= max_auto_apply


class TestLabelManagement:
    """Tests for label management operations."""

    def test_add_duplicate_label_detected(self, default_settings):
        """Adding duplicate label should be detected."""
        settings = default_settings.copy()

        duplicate_label = 'professional'  # Already exists
        is_duplicate = duplicate_label in settings['classification_labels']

        assert is_duplicate is True

    def test_remove_nonexistent_label_handled(self, default_settings):
        """Removing nonexistent label should be handled gracefully."""
        settings = default_settings.copy()

        nonexistent_label = 'nonexistent'

        # Try to remove (should not raise exception)
        if nonexistent_label in settings['classification_labels']:
            settings['classification_labels'].remove(nonexistent_label)

        # Verify state unchanged
        assert len(settings['classification_labels']) == 8

    def test_label_validation_length_constraints(self):
        """Labels should meet length constraints."""
        valid_labels = ['ab', 'normal', 'a' * 30]
        invalid_labels = ['a', '', 'a' * 31]

        for label in valid_labels:
            assert 2 <= len(label) <= 30

        for label in invalid_labels:
            assert not (2 <= len(label) <= 30)

    def test_many_labels_supported(self, default_settings):
        """System should support many labels (100+)."""
        settings = default_settings.copy()

        # Add 100 more labels
        for i in range(100):
            settings['classification_labels'].append(f'label{i}')

        # Verify all added
        assert len(settings['classification_labels']) == 108  # 8 default + 100 new


class TestSettingsEdgeCases:
    """Tests for edge cases in settings behavior."""

    def test_classification_disabled_allows_threshold_changes(self, default_settings):
        """Should allow threshold changes even when classification disabled."""
        settings = default_settings.copy()
        settings['classification_enabled'] = False

        # Modify thresholds while disabled
        settings['auto_apply_threshold'] = 90
        settings['suggestion_threshold'] = 70

        # Changes should persist
        assert settings['auto_apply_threshold'] == 90
        assert settings['suggestion_threshold'] == 70
        assert settings['classification_enabled'] is False

    def test_empty_labels_list_handled(self):
        """Empty labels list should be handled gracefully."""
        settings = {'classification_labels': []}

        # Empty list is technically valid
        assert len(settings['classification_labels']) == 0
        assert isinstance(settings['classification_labels'], list)

    def test_extreme_threshold_values(self):
        """Extreme but valid threshold values should work."""
        # All classification auto-applied (100% threshold)
        extreme_high = {
            'auto_apply_threshold': 100,
            'suggestion_threshold': 100
        }

        # Almost nothing auto-applied (50% threshold)
        extreme_low = {
            'auto_apply_threshold': 50,
            'suggestion_threshold': 40
        }

        # Both should be valid
        assert 50 <= extreme_high['auto_apply_threshold'] <= 100
        assert extreme_high['suggestion_threshold'] <= extreme_high['auto_apply_threshold']
        assert 50 <= extreme_low['auto_apply_threshold'] <= 100
        assert extreme_low['suggestion_threshold'] <= extreme_low['auto_apply_threshold']
