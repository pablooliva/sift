#!/usr/bin/env python
"""Test script to create and verify txtai index with SQLite storage"""

import requests
import json
import time
import os

API_URL = os.environ.get("TXTAI_API_URL", "http://localhost:9301")

def test_index():
    # First, let's check the current config
    print("Testing txtai index creation and SQLite storage...")

    # Try to add documents
    documents = [
        {"id": "1", "text": "The quick brown fox jumps over the lazy dog"},
        {"id": "2", "text": "Machine learning is a subset of artificial intelligence"},
        {"id": "3", "text": "Python is a popular programming language for data science"}
    ]

    print("\n1. Adding documents...")
    response = requests.post(f"{API_URL}/add", json=documents)
    print(f"   Response: {response.status_code} - {response.text}")

    # Try to build the index
    print("\n2. Building index...")
    response = requests.get(f"{API_URL}/index")
    print(f"   Response: {response.status_code} - {response.text}")

    # Try to search
    print("\n3. Testing search...")
    response = requests.get(f"{API_URL}/search", params={"query": "python programming", "limit": 3})
    print(f"   Response: {response.status_code}")
    if response.status_code == 200:
        results = response.json()
        print(f"   Results: {json.dumps(results, indent=2)}")
    else:
        print(f"   Error: {response.text}")

    # Check document count
    print("\n4. Checking document count...")
    response = requests.get(f"{API_URL}/count")
    print(f"   Response: {response.status_code} - {response.text}")

if __name__ == "__main__":
    test_index()