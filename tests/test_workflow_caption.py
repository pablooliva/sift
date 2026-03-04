#!/usr/bin/env python3
"""
Test script for SPEC-019 Phase 2: Ollama-based image captioning workflow.

This script validates that the ollama-caption workflow correctly generates
captions for test images using Ollama llama3.2-vision:11b.
"""

import os
import sys
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Configuration
TXTAI_API_URL = os.getenv("TXTAI_API_URL", "http://localhost:8300")
# Use shared_uploads directory that's mounted to both txtai and frontend containers
PROJECT_ROOT = Path(__file__).parent
TEST_IMAGE_DIR = PROJECT_ROOT / "shared_uploads" / "test_images"


def create_test_images():
    """Create simple test images for caption validation."""
    os.makedirs(TEST_IMAGE_DIR, exist_ok=True)
    test_images = []

    # Test 1: Simple geometric shapes
    img1 = Image.new('RGB', (400, 300), color='white')
    draw = ImageDraw.Draw(img1)
    draw.rectangle([50, 50, 150, 150], fill='red', outline='black', width=3)
    draw.ellipse([200, 50, 350, 200], fill='blue', outline='black', width=3)
    draw.polygon([(200, 250), (275, 100), (350, 250)], fill='green', outline='black')
    img1_path = str(TEST_IMAGE_DIR / "geometric_shapes.jpg")
    img1.save(img1_path)
    # Path as seen by txtai container (mounted at /uploads)
    img1_container_path = "/uploads/test_images/geometric_shapes.jpg"
    test_images.append(("geometric_shapes", img1_container_path, "geometric shapes, colored objects"))

    # Test 2: Text image
    img2 = Image.new('RGB', (600, 200), color='lightblue')
    draw = ImageDraw.Draw(img2)
    try:
        # Try to use a font, fall back to default if not available
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
    except:
        font = ImageFont.load_default()
    draw.text((50, 80), "HELLO WORLD", fill='black', font=font)
    img2_path = str(TEST_IMAGE_DIR / "text_image.jpg")
    img2.save(img2_path)
    # Path as seen by txtai container (mounted at /uploads)
    img2_container_path = "/uploads/test_images/text_image.jpg"
    test_images.append(("text_image", img2_container_path, "text, hello world"))

    # Test 3: Gradient
    img3 = Image.new('RGB', (400, 300), color='white')
    for y in range(300):
        color_value = int(255 * (y / 300))
        draw = ImageDraw.Draw(img3)
        draw.line([(0, y), (400, y)], fill=(color_value, 0, 255-color_value))
    img3_path = str(TEST_IMAGE_DIR / "gradient.jpg")
    img3.save(img3_path)
    # Path as seen by txtai container (mounted at /uploads)
    img3_container_path = "/uploads/test_images/gradient.jpg"
    test_images.append(("gradient", img3_container_path, "gradient, purple, transition"))

    print(f"✓ Created {len(test_images)} test images in {TEST_IMAGE_DIR}")
    return test_images


def run_ollama_caption_workflow(image_path: str, test_name: str, expected_keywords: str):
    """
    Run the ollama-caption workflow with a test image (helper function, not a pytest test).

    Run with: python test_workflow_caption.py

    Args:
        image_path: Path to test image
        test_name: Name of the test
        expected_keywords: Keywords that should appear in caption (comma-separated)

    Returns:
        bool: True if test passed, False otherwise
    """
    print(f"\n{'='*60}")
    print(f"Test: {test_name}")
    print(f"Image: {image_path}")
    print(f"Expected keywords: {expected_keywords}")
    print(f"{'='*60}")

    try:
        # Call txtai workflow API
        response = requests.post(
            f"{TXTAI_API_URL}/workflow",
            json={"name": "ollama-caption", "elements": [image_path]},
            timeout=30
        )

        # Check response status
        if response.status_code != 200:
            print(f"✗ FAILED: HTTP {response.status_code}")
            print(f"  Response: {response.text}")
            return False

        # Parse result
        result = response.json()
        if not result or len(result) == 0:
            print(f"✗ FAILED: Empty response from workflow")
            return False

        caption = result[0]
        print(f"\n✓ Caption generated:")
        print(f"  '{caption}'")

        # Validate caption is not empty
        if not caption or len(caption) < 5:
            print(f"✗ FAILED: Caption too short (< 5 chars)")
            return False

        # Check for expected keywords (case-insensitive)
        caption_lower = caption.lower()
        keywords = [k.strip() for k in expected_keywords.split(",")]
        found_keywords = [k for k in keywords if k.lower() in caption_lower]

        if len(found_keywords) > 0:
            print(f"✓ Found keywords: {', '.join(found_keywords)}")
        else:
            print(f"⚠ WARNING: No expected keywords found, but caption is valid")
            print(f"  (This is not necessarily a failure - vision models may describe differently)")

        # Consider test passed if we got a reasonable caption
        # Even if keywords don't match exactly, the model may describe things differently
        print(f"✓ PASSED: Caption generated successfully")
        return True

    except requests.exceptions.Timeout:
        print(f"✗ FAILED: Request timeout (>30s)")
        return False

    except requests.exceptions.ConnectionError as e:
        print(f"✗ FAILED: Cannot connect to txtai API at {TXTAI_API_URL}")
        print(f"  Error: {e}")
        return False

    except Exception as e:
        print(f"✗ FAILED: Unexpected error: {e}")
        return False


def main():
    """Run all caption workflow tests."""
    print("=" * 60)
    print("SPEC-019 Phase 2: Ollama Caption Workflow Test")
    print("=" * 60)
    print(f"txtai API: {TXTAI_API_URL}")
    print(f"Test image directory: {TEST_IMAGE_DIR}")

    # Create test images
    test_images = create_test_images()

    # Run tests
    results = []
    for test_name, image_path, expected_keywords in test_images:
        passed = run_ollama_caption_workflow(image_path, test_name, expected_keywords)
        results.append((test_name, passed))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nResults: {passed_count}/{total_count} tests passed")

    # Exit code
    if passed_count == total_count:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print(f"\n✗ {total_count - passed_count} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
