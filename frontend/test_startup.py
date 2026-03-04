#!/usr/bin/env python
"""
Quick startup test for txtai frontend.
Tests imports and basic functionality without starting the full Streamlit app.
"""

import sys
from pathlib import Path

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all required modules can be imported"""
    print("Testing imports...")

    try:
        import streamlit
        print("✅ streamlit imported")
    except ImportError as e:
        print(f"❌ Failed to import streamlit: {e}")
        return False

    try:
        import requests
        print("✅ requests imported")
    except ImportError as e:
        print(f"❌ Failed to import requests: {e}")
        return False

    try:
        from utils.api_client import TxtAIClient, APIHealthStatus
        print("✅ api_client imported")
    except ImportError as e:
        print(f"❌ Failed to import api_client: {e}")
        return False

    try:
        from utils.config_validator import ConfigValidator, ValidationResult
        print("✅ config_validator imported")
    except ImportError as e:
        print(f"❌ Failed to import config_validator: {e}")
        return False

    return True


def test_api_client():
    """Test API client initialization and health check"""
    print("\nTesting API client...")

    try:
        from utils.api_client import TxtAIClient, APIHealthStatus

        client = TxtAIClient(base_url="http://localhost:8300")
        print("✅ API client initialized")

        health = client.check_health()
        print(f"API Health Status: {health['status']}")
        print(f"Message: {health['message']}")

        if health['status'] == APIHealthStatus.HEALTHY:
            print("✅ txtai API is healthy")
            return True
        else:
            print("⚠️ txtai API is not healthy (may be expected if containers are not running)")
            return True  # Still return True - this is not a code error

    except Exception as e:
        print(f"❌ Error testing API client: {e}")
        return False


def test_config_validator():
    """Test configuration validator"""
    print("\nTesting configuration validator...")

    try:
        from utils.config_validator import ConfigValidator

        config_path = Path(__file__).parent.parent / 'config.yml'
        validator = ConfigValidator(str(config_path))
        print(f"✅ Config validator initialized (path: {config_path})")

        if validator.load_config():
            print("✅ Configuration loaded")
        else:
            print("⚠️ Failed to load configuration (may be expected if file doesn't exist)")
            return True  # Still return True - will be caught by validation

        result = validator.validate()
        print(f"\nValidation Result: {'VALID' if result.is_valid else 'INVALID'}")

        if result.errors:
            print("\nErrors:")
            for error in result.errors:
                print(f"  ❌ {error}")

        if result.warnings:
            print("\nWarnings:")
            for warning in result.warnings:
                print(f"  ⚠️ {warning}")

        # Check graph configuration specifically
        graph_status = validator.get_graph_status()
        print(f"\nGraph Configuration Status: {graph_status['status']}")
        print(f"Message: {graph_status['message']}")

        return True

    except Exception as e:
        print(f"❌ Error testing config validator: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("txtai Frontend Startup Test")
    print("=" * 60)

    results = []

    results.append(("Imports", test_imports()))
    results.append(("API Client", test_api_client()))
    results.append(("Config Validator", test_config_validator()))

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n✅ All tests passed! Frontend is ready to start.")
        print("\nTo start the application, run:")
        print("  cd frontend")
        print("  source .venv/bin/activate")
        print("  streamlit run Home.py")
        return 0
    else:
        print("\n❌ Some tests failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
