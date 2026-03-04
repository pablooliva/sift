#!/usr/bin/env python3
"""
Test script for txtai audio transcription via API.

This script demonstrates how to:
1. Upload an audio file for transcription
2. Get the transcribed text from txtai API
3. Add the transcribed content to the txtai index
"""

import requests
import json
import sys
from pathlib import Path

TXTAI_API_URL = "http://localhost:8300"

def transcribe_audio_file(audio_file_path: str) -> str:
    """
    Transcribe an audio file using txtai's transcribe endpoint.

    Note: The txtai /transcribe endpoint expects a file path that's accessible
    to the txtai container. For local files, they need to be in a mounted volume.

    Args:
        audio_file_path: Path to the audio file (must be accessible to txtai container)

    Returns:
        Transcribed text
    """
    print(f"Transcribing audio file: {audio_file_path}")

    # Call the transcribe endpoint
    response = requests.get(
        f"{TXTAI_API_URL}/transcribe",
        params={"file": audio_file_path}
    )

    if response.status_code == 200:
        transcription = response.json()
        print(f"✓ Transcription successful!")
        print(f"Transcribed text length: {len(transcription)} characters")
        return transcription
    else:
        print(f"✗ Transcription failed: {response.status_code}")
        print(f"Error: {response.text}")
        return None


def add_to_index(text: str, metadata: dict) -> bool:
    """
    Add transcribed text to the txtai index.

    Args:
        text: The transcribed text
        metadata: Metadata to associate with the document

    Returns:
        True if successful, False otherwise
    """
    print("Adding transcribed content to txtai index...")

    # Prepare the document
    documents = [{
        "text": text,
        **metadata
    }]

    # Add to index
    response = requests.post(
        f"{TXTAI_API_URL}/add",
        json=documents
    )

    if response.status_code == 200:
        print("✓ Successfully added to index")

        # Index the new content
        index_response = requests.get(f"{TXTAI_API_URL}/index")
        if index_response.status_code == 200:
            print("✓ Index updated")
            return True
        else:
            print(f"✗ Index update failed: {index_response.status_code}")
            return False
    else:
        print(f"✗ Failed to add to index: {response.status_code}")
        print(f"Error: {response.text}")
        return False


def run_workflow(audio_file_path: str):
    """
    Run the complete workflow: transcribe → add to index → search.

    Note: This is a standalone script helper, not a pytest test.
    Run with: python test_audio_transcription.py <audio_file_path>

    Args:
        audio_file_path: Path to audio file (relative to txtai container)
    """
    print("\n" + "="*60)
    print("txtai Audio Transcription Test")
    print("="*60 + "\n")

    # Step 1: Transcribe
    transcription = transcribe_audio_file(audio_file_path)
    if not transcription:
        print("\n✗ Test failed: Could not transcribe audio")
        return False

    print(f"\nFirst 200 characters of transcription:")
    print(f"{transcription[:200]}...\n")

    # Step 2: Add to index
    metadata = {
        "filename": Path(audio_file_path).name,
        "source": "api_test",
        "type": "audio_transcription"
    }

    success = add_to_index(transcription, metadata)
    if not success:
        print("\n✗ Test failed: Could not add to index")
        return False

    # Step 3: Test search
    print("\nTesting search functionality...")
    search_query = transcription.split()[0:5]  # First few words
    search_text = " ".join(search_query) if isinstance(search_query, list) else str(transcription)[:50]

    response = requests.get(
        f"{TXTAI_API_URL}/search",
        params={"query": search_text, "limit": 1}
    )

    if response.status_code == 200:
        results = response.json()
        if results:
            print(f"✓ Search successful! Found {len(results)} result(s)")
            print(f"  Score: {results[0].get('score', 'N/A')}")
        else:
            print("⚠ Search returned no results (index may need time to update)")
    else:
        print(f"✗ Search failed: {response.status_code}")

    print("\n" + "="*60)
    print("✓ Test completed successfully!")
    print("="*60 + "\n")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_audio_transcription.py <audio_file_path>")
        print("\nExample:")
        print("  python test_audio_transcription.py /data/test.mp3")
        print("\nNote: The file path must be accessible to the txtai container.")
        print("      For testing, place files in the ./txtai_data directory.")
        sys.exit(1)

    audio_file = sys.argv[1]
    run_workflow(audio_file)
