#!/usr/bin/env python3
"""
Test Phase 4: Settings UI Integration

Validates SPEC-012 Phase 4 requirements:
- REQ-009: Label management UI
- REQ-011: Enable/disable toggle
- REQ-012: Confidence threshold configuration
- Settings integration with Upload workflow
"""

import sys
from pathlib import Path

# Project root is parent of tests/ directory
PROJECT_ROOT = Path(__file__).parent.parent

def test_settings_page_exists():
    """Test that Settings page file was created"""
    settings_path = PROJECT_ROOT / "frontend" / "pages" / "5_⚙️_Settings.py"
    assert settings_path.exists(), f"Settings page not found at {settings_path}"
    print("✓ Settings page file exists")

def test_settings_page_structure():
    """Test that Settings page contains required components"""
    settings_path = PROJECT_ROOT / "frontend" / "pages" / "5_⚙️_Settings.py"

    with open(settings_path, 'r') as f:
        content = f.read()

    # REQ-011: Enable/disable toggle
    assert 'classification_enabled' in content, "Missing classification_enabled toggle"
    assert 'st.toggle' in content, "Missing Streamlit toggle component"
    print("✓ REQ-011: Enable/disable toggle present")

    # REQ-009: Label management
    assert 'classification_labels' in content, "Missing classification_labels"
    assert 'new_label' in content, "Missing new label input"
    assert 'Add Label' in content or 'Add New Label' in content, "Missing add label button"
    print("✓ REQ-009: Label management UI present")

    # REQ-012: Confidence thresholds
    assert 'auto_apply_threshold' in content, "Missing auto_apply_threshold"
    assert 'suggestion_threshold' in content, "Missing suggestion_threshold"
    assert 'st.slider' in content, "Missing threshold slider components"
    print("✓ REQ-012: Confidence threshold configuration present")

    # Help documentation
    assert 'About Auto-Classification' in content or 'How it works' in content, "Missing help documentation"
    print("✓ Help documentation present")

def test_upload_integration():
    """Test that Upload.py uses settings from session_state"""
    upload_path = PROJECT_ROOT / "frontend" / "pages" / "1_📤_Upload.py"

    with open(upload_path, 'r') as f:
        content = f.read()

    # Check for settings integration
    # REQ-011: Enable/disable classification toggle
    assert "st.session_state.get('classification_enabled'" in content, \
        "Upload doesn't check classification_enabled setting"
    print("✓ Upload checks classification_enabled (REQ-011)")

    # REQ-012: Suggestion threshold for classification confidence
    assert "st.session_state.get('suggestion_threshold'" in content, \
        "Upload doesn't use suggestion_threshold setting"
    print("✓ Upload uses suggestion_threshold (REQ-012)")

def test_default_values():
    """Test that default values match SPEC-012"""
    settings_path = PROJECT_ROOT / "frontend" / "pages" / "5_⚙️_Settings.py"

    with open(settings_path, 'r') as f:
        content = f.read()

    # Default thresholds per SPEC-012
    assert "'auto_apply_threshold', 85)" in content or \
           "auto_apply_threshold = 85" in content, \
        "Default auto_apply_threshold should be 85%"
    print("✓ Default auto_apply_threshold = 85%")

    assert "'suggestion_threshold', 60)" in content or \
           "suggestion_threshold = 60" in content, \
        "Default suggestion_threshold should be 60%"
    print("✓ Default suggestion_threshold = 60%")

    # Default labels from SPEC-012
    expected_labels = ["professional", "personal", "financial", "legal",
                      "reference", "project", "activism"]
    for label in expected_labels:
        assert label in content, f"Default label '{label}' not found"
    print(f"✓ All {len(expected_labels)} default labels present")

def test_ui_components():
    """Test that Settings page has proper UI structure"""
    settings_path = PROJECT_ROOT / "frontend" / "pages" / "5_⚙️_Settings.py"

    with open(settings_path, 'r') as f:
        content = f.read()

    # Page structure
    assert 'st.title' in content, "Missing page title"
    assert 'st.header' in content, "Missing section headers"
    assert 'st.divider' in content, "Missing section dividers"
    print("✓ Page structure components present")

    # Reset functionality
    assert 'Reset' in content, "Missing reset functionality"
    print("✓ Reset functionality present")

    # Visual feedback
    assert 'st.success' in content, "Missing success messages"
    assert 'st.info' in content or 'st.warning' in content, "Missing info/warning messages"
    print("✓ User feedback messages present")

def test_session_state_initialization():
    """Test that session state is properly initialized"""
    settings_path = PROJECT_ROOT / "frontend" / "pages" / "5_⚙️_Settings.py"

    with open(settings_path, 'r') as f:
        content = f.read()

    # All required session state variables
    required_state = [
        'classification_enabled',
        'classification_labels',
        'auto_apply_threshold',
        'suggestion_threshold'
    ]

    for state_var in required_state:
        assert f"'{state_var}' not in st.session_state" in content, \
            f"Missing session_state initialization for {state_var}"
    print(f"✓ All {len(required_state)} session state variables initialized")

def test_yaml_config_loading():
    """Test that Settings page can load defaults from config.yml"""
    settings_path = PROJECT_ROOT / "frontend" / "pages" / "5_⚙️_Settings.py"

    with open(settings_path, 'r') as f:
        content = f.read()

    assert 'import yaml' in content, "Missing yaml import"
    assert 'load_default_labels' in content or 'yaml.safe_load' in content, \
        "Missing config.yml loading logic"
    print("✓ Config.yml loading implemented")

def run_all_tests():
    """Run all Phase 4 tests"""
    print("\n=== Phase 4: Settings UI Tests ===\n")

    tests = [
        ("Settings Page Exists", test_settings_page_exists),
        ("Settings Page Structure", test_settings_page_structure),
        ("Upload Integration", test_upload_integration),
        ("Default Values", test_default_values),
        ("UI Components", test_ui_components),
        ("Session State Init", test_session_state_initialization),
        ("YAML Config Loading", test_yaml_config_loading),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            print(f"\n{test_name}:")
            test_func()
            passed += 1
            print(f"✓ {test_name} PASSED\n")
        except AssertionError as e:
            failed += 1
            print(f"✗ {test_name} FAILED: {e}\n")
        except Exception as e:
            failed += 1
            print(f"✗ {test_name} ERROR: {e}\n")

    print("=" * 50)
    print(f"\nResults: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 50)

    if failed == 0:
        print("\n🎉 Phase 4: Settings UI - ALL TESTS PASSED ✓\n")
        print("Requirements completed:")
        print("  ✓ REQ-009: Label management UI")
        print("  ✓ REQ-011: Enable/disable toggle")
        print("  ✓ REQ-012: Confidence threshold configuration")
        print("  ✓ Settings integration with Upload workflow")
        print("\nNext: Phase 5 - Polish + Testing")
        return 0
    else:
        print("\n❌ Some tests failed. Please review and fix.\n")
        return 1

if __name__ == "__main__":
    sys.exit(run_all_tests())
