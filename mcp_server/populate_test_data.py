#!/usr/bin/env python3
"""
Populate txtai with test documents to generate Graphiti entities and relationships.
Creates documents about a fictional tech company with interconnected content.
"""

import requests
import json
import time
from datetime import datetime

TXTAI_API_URL = "http://localhost:8300"

# Test documents with related content for entity extraction
TEST_DOCUMENTS = [
    {
        "id": "doc-001",
        "text": """
TechCorp Inc. Overview

TechCorp Inc. is a leading artificial intelligence company founded in 2020 by Dr. Sarah Chen and
Dr. Marcus Johnson. The company specializes in machine learning solutions for healthcare and finance.
Headquartered in San Francisco, TechCorp employs over 200 engineers and data scientists.

The company's flagship product, MedAI, uses deep learning to analyze medical images and assist
radiologists in early disease detection. TechCorp secured $50 million in Series B funding led by
Venture Capital Partners in 2023.
        """.strip(),
        "title": "TechCorp Inc. Company Profile",
        "metadata": {"category": "Company Info", "date": "2024-01-15"}
    },
    {
        "id": "doc-002",
        "text": """
MedAI Product Launch

TechCorp Inc. announced the official launch of MedAI v2.0, their revolutionary medical imaging
analysis platform. The system was developed by Lead Engineer Dr. Sarah Chen and her team over
18 months.

MedAI uses convolutional neural networks and transformer architectures to analyze X-rays, CT scans,
and MRI images with 95% accuracy. The platform integrates with major hospital information systems
including Epic and Cerner.

Dr. Chen stated, "MedAI represents a breakthrough in AI-assisted diagnostics. Our partnership with
Stanford Medical Center validates the clinical efficacy of our approach."
        """.strip(),
        "title": "MedAI v2.0 Product Launch Announcement",
        "metadata": {"category": "Product News", "date": "2024-02-20"}
    },
    {
        "id": "doc-003",
        "text": """
TechCorp Engineering Team

The TechCorp engineering organization is led by VP of Engineering Dr. Marcus Johnson, who previously
worked at Google Brain. The team is organized into three divisions:

1. Machine Learning Research: Led by Dr. Sarah Chen, focuses on computer vision and medical AI
2. Platform Engineering: Led by Alex Rivera, builds scalable cloud infrastructure on AWS
3. Data Engineering: Led by Dr. Priya Patel, manages data pipelines and model training infrastructure

Recent hires include two PhDs from MIT's Computer Science and Artificial Intelligence Laboratory (CSAIL)
and three senior engineers from DeepMind. The team uses Python, PyTorch, and TensorFlow for model
development.
        """.strip(),
        "title": "TechCorp Engineering Organization",
        "metadata": {"category": "Team", "date": "2024-03-10"}
    },
    {
        "id": "doc-004",
        "text": """
Stanford Medical Center Partnership

TechCorp Inc. announced a strategic partnership with Stanford Medical Center to deploy MedAI in
their radiology department. The three-year collaboration will involve:

- Clinical validation studies with 10,000+ patient cases
- Integration with Stanford's Epic EHR system
- Joint research publications with Stanford researchers
- Training for 50+ radiologists on AI-assisted diagnostics

Dr. Robert Lee, Chief of Radiology at Stanford, praised the partnership: "MedAI's deep learning
capabilities complement our radiologists' expertise. This collaboration with Dr. Sarah Chen's team
will advance the field of medical imaging."

The partnership was facilitated by Venture Capital Partners, TechCorp's lead investor.
        """.strip(),
        "title": "Stanford Medical Center Partnership Announcement",
        "metadata": {"category": "Partnership", "date": "2024-04-05"}
    },
    {
        "id": "doc-005",
        "text": """
TechCorp Funding and Growth

TechCorp Inc. secured $50 million in Series B funding led by Venture Capital Partners, with
participation from Healthcare Innovation Fund and AI Ventures. The round values the company at
$250 million.

CEO Dr. Sarah Chen announced plans to use the funding to:
- Expand the engineering team from 200 to 300 employees
- Launch MedAI in European markets through partnerships with NHS and German healthcare systems
- Develop new AI models for cardiology and oncology imaging
- Scale AWS infrastructure to support 100+ hospital deployments

Dr. Marcus Johnson, VP of Engineering, stated: "This funding accelerates our mission to make
AI-assisted diagnostics accessible to every hospital globally."
        """.strip(),
        "title": "TechCorp Series B Funding Announcement",
        "metadata": {"category": "Funding", "date": "2024-05-15"}
    }
]


def add_documents():
    """Add documents to txtai via API."""
    print(f"📤 Adding {len(TEST_DOCUMENTS)} test documents to txtai...")

    # Format documents for txtai API
    documents = [
        {
            "id": doc["id"],
            "text": doc["text"],
            "title": doc.get("title", ""),
            **doc.get("metadata", {})
        }
        for doc in TEST_DOCUMENTS
    ]

    response = requests.post(
        f"{TXTAI_API_URL}/add",
        json=documents,
        timeout=30
    )
    response.raise_for_status()
    print(f"✅ Documents added successfully")
    return response.json()


def build_index():
    """Build the txtai index."""
    print("🔨 Building txtai index...")
    response = requests.get(f"{TXTAI_API_URL}/index", timeout=60)
    response.raise_for_status()
    print("✅ Index built successfully")
    return response.json()


def check_count():
    """Check document count."""
    response = requests.get(f"{TXTAI_API_URL}/count", timeout=10)
    response.raise_for_status()
    count = int(response.text)
    print(f"📊 Document count: {count}")
    return count


def main():
    print("\n🚀 Populating txtai with test data...")
    print(f"📍 txtai API: {TXTAI_API_URL}")
    print()

    try:
        # Check initial count
        initial_count = check_count()

        if initial_count > 0:
            print("⚠️  Index already has documents. Clear it first if you want fresh data.")
            response = input("Continue anyway? (y/n): ").lower()
            if response != 'y':
                print("❌ Aborted")
                return

        # Add documents
        add_documents()

        # Build index (this triggers Graphiti ingestion in the background)
        build_index()

        # Check final count
        print()
        final_count = check_count()

        print()
        print("✅ Test data populated successfully!")
        print(f"📊 Total documents: {final_count}")
        print()
        print("⏳ Note: Graphiti ingestion runs in background and takes ~10-15 minutes")
        print("   for 5 documents. Check Neo4j to monitor progress:")
        print("   http://localhost:7474")
        print()

    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
