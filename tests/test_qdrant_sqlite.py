#!/usr/bin/env python
"""
Test script to verify Qdrant + SQLite integration after fixing search_batch

DEPRECATION NOTICE:
This test is for a HISTORICAL configuration (Qdrant + SQLite hybrid).
The current production configuration uses PostgreSQL instead of SQLite for content storage.
See config.yml line 11: content: postgresql+psycopg2://postgres:postgres@postgres:5432/txtai

This test is kept for reference but does NOT reflect the active storage configuration.
For the current setup, see docs/DATA_STORAGE_GUIDE.md
"""

import requests
import json
import time
import sqlite3
import os

API_URL = "http://localhost:8300"
QDRANT_URL = "http://localhost:6333"
SQLITE_PATH = "./txtai_data/index/documents"

def test_qdrant_sqlite():
    print("=" * 60)
    print("Testing Qdrant + SQLite Integration")
    print("=" * 60)

    # 1. Check Qdrant is running
    print("\n1. Checking Qdrant status...")
    try:
        response = requests.get(f"{QDRANT_URL}/collections")
        print(f"   ✓ Qdrant is running. Collections: {response.status_code}")
    except Exception as e:
        print(f"   ✗ Qdrant not accessible: {e}")
        return

    # 2. Check txtai API is running
    print("\n2. Checking txtai API status...")
    try:
        response = requests.get(f"{API_URL}/")
        print(f"   ✓ txtai API is running")
    except Exception as e:
        print(f"   ✗ txtai API not accessible: {e}")
        return

    # 3. Add test documents
    print("\n3. Adding test documents...")
    documents = [
        {"id": "doc1", "text": "Qdrant is a vector database for similarity search", "metadata": {"type": "database"}},
        {"id": "doc2", "text": "SQLite stores document content and metadata", "metadata": {"type": "storage"}},
        {"id": "doc3", "text": "Python is great for data science and machine learning", "metadata": {"type": "language"}},
        {"id": "doc4", "text": "txtai combines embeddings with full-text search", "metadata": {"type": "framework"}},
    ]

    response = requests.post(f"{API_URL}/add", json=documents)
    if response.status_code == 200:
        print(f"   ✓ Documents added successfully")
    else:
        print(f"   ✗ Failed to add documents: {response.text}")
        return

    # 4. Build index
    print("\n4. Building index...")
    response = requests.get(f"{API_URL}/index")
    if response.status_code == 200:
        print(f"   ✓ Index built successfully")
    else:
        print(f"   ✗ Failed to build index: {response.text}")
        return

    # Give it a moment to complete indexing
    time.sleep(2)

    # 5. Test search (this will use Qdrant)
    print("\n5. Testing vector search (Qdrant)...")
    response = requests.get(f"{API_URL}/search", params={"query": "database storage", "limit": 3})
    if response.status_code == 200:
        results = response.json()
        print(f"   ✓ Search successful. Results:")
        for result in results:
            print(f"      - ID: {result['id']}, Score: {result['score']:.4f}")
            if 'text' in result:
                print(f"        Text: {result['text'][:60]}...")
    else:
        print(f"   ✗ Search failed: {response.text}")

    # 6. Check Qdrant collection
    print("\n6. Verifying Qdrant collection...")
    response = requests.get(f"{QDRANT_URL}/collections/txtai_embeddings")
    if response.status_code == 200:
        data = response.json()
        points_count = data['result']['points_count']
        print(f"   ✓ Qdrant collection has {points_count} vectors")
    else:
        print(f"   ✗ Could not check Qdrant collection")

    # 7. Check SQLite database
    print("\n7. Verifying SQLite database...")
    if os.path.exists(SQLITE_PATH):
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            cursor = conn.cursor()

            # Check document count
            cursor.execute("SELECT COUNT(*) FROM documents")
            count = cursor.fetchone()[0]
            print(f"   ✓ SQLite database exists with {count} documents")

            # Show sample data
            cursor.execute("SELECT id, json_extract(data, '$.text') FROM documents LIMIT 2")
            print("   Sample documents:")
            for row in cursor.fetchall():
                print(f"      - ID: {row[0]}")
                print(f"        Text: {row[1][:60]}...")

            conn.close()
        except Exception as e:
            print(f"   ✗ Error reading SQLite: {e}")
    else:
        print(f"   ✗ SQLite database not found at {SQLITE_PATH}")

    # 8. Test document retrieval
    print("\n8. Testing document count...")
    response = requests.get(f"{API_URL}/count")
    if response.status_code == 200:
        count = response.text
        print(f"   ✓ Document count: {count}")
    else:
        print(f"   ✗ Could not get document count")

    print("\n" + "=" * 60)
    print("✅ Qdrant + SQLite Integration Test Complete!")
    print("=" * 60)

if __name__ == "__main__":
    test_qdrant_sqlite()