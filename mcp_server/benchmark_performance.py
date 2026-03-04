#!/usr/bin/env python3
"""
Performance benchmarking script for SPEC-037 MCP Graphiti integration.

Tests:
1. knowledge_graph_search latency
2. search with include_graph_context (parallel query overhead)
3. rag_query with include_graph_context (enrichment latency)

Usage:
    export NEO4J_URI="bolt://localhost:7687"
    export NEO4J_USER="neo4j"
    export NEO4J_PASSWORD="your-password"
    export TXTAI_API_URL="http://localhost:8300"
    export TOGETHERAI_API_KEY="your-api-key"

    python benchmark_performance.py
"""

import asyncio
import os
import sys
import time
from statistics import mean, median, stdev
from typing import List, Dict, Any

# Add mcp_server to path
sys.path.insert(0, os.path.dirname(__file__))

# Import MCP server tools
from txtai_rag_mcp import (
    knowledge_graph_search,
    search,
    rag_query,
    get_graphiti_client,
)


class PerformanceBenchmark:
    """Performance benchmarking for Graphiti integration."""

    def __init__(self):
        self.results: Dict[str, List[float]] = {
            'knowledge_graph_search': [],
            'search_no_context': [],
            'search_with_context': [],
            'rag_no_context': [],
            'rag_with_context': [],
        }

    async def benchmark_knowledge_graph_search(self, query: str, iterations: int = 5):
        """Benchmark knowledge_graph_search tool."""
        print(f"\n🔍 Benchmarking knowledge_graph_search ('{query}', {iterations} iterations)...")

        for i in range(iterations):
            start = time.perf_counter()
            result = await knowledge_graph_search(query=query, limit=15)
            elapsed = (time.perf_counter() - start) * 1000  # ms

            self.results['knowledge_graph_search'].append(elapsed)

            # Log result info
            entities = len(result.get('entities', []))
            relationships = len(result.get('relationships', []))
            status = result.get('graphiti_status', 'success')
            print(f"  Iteration {i+1}: {elapsed:.0f}ms (entities: {entities}, relationships: {relationships}, status: {status})")

        self._print_stats('knowledge_graph_search', target_ms=2000)

    async def benchmark_search_enrichment(self, query: str, iterations: int = 5):
        """Benchmark search with and without graph context."""
        print(f"\n📄 Benchmarking search enrichment ('{query}', {iterations} iterations)...")

        # Without enrichment (baseline)
        print("  Without enrichment:")
        for i in range(iterations):
            start = time.perf_counter()
            result = await search(query=query, limit=10, include_graph_context=False)
            elapsed = (time.perf_counter() - start) * 1000

            self.results['search_no_context'].append(elapsed)
            print(f"    Iteration {i+1}: {elapsed:.0f}ms (results: {len(result.get('results', []))})")

        # With enrichment
        print("  With enrichment:")
        for i in range(iterations):
            start = time.perf_counter()
            result = await search(query=query, limit=10, include_graph_context=True)
            elapsed = (time.perf_counter() - start) * 1000

            self.results['search_with_context'].append(elapsed)

            # Check enrichment metadata
            metadata = result.get('enrichment_metadata', {})
            status = metadata.get('graphiti_status', 'unknown')
            print(f"    Iteration {i+1}: {elapsed:.0f}ms (status: {status})")

        # Calculate overhead
        baseline_avg = mean(self.results['search_no_context'])
        enriched_avg = mean(self.results['search_with_context'])
        overhead = enriched_avg - baseline_avg

        print(f"\n  Baseline (no enrichment): {baseline_avg:.0f}ms")
        print(f"  Enriched (with context):  {enriched_avg:.0f}ms")
        print(f"  Overhead:                 {overhead:.0f}ms (target: <500ms)")
        print(f"  Status: {'✅ PASS' if overhead < 500 else '⚠️  ABOVE TARGET'}")

    async def benchmark_rag_enrichment(self, query: str, iterations: int = 3):
        """Benchmark rag_query with and without graph context."""
        print(f"\n💬 Benchmarking RAG enrichment ('{query}', {iterations} iterations)...")

        # Without enrichment (baseline)
        print("  Without enrichment:")
        for i in range(iterations):
            start = time.perf_counter()
            result = await rag_query(query=query, include_graph_context=False)
            elapsed = (time.perf_counter() - start) * 1000

            self.results['rag_no_context'].append(elapsed)
            print(f"    Iteration {i+1}: {elapsed:.0f}ms")

        # With enrichment
        print("  With enrichment:")
        for i in range(iterations):
            start = time.perf_counter()
            result = await rag_query(query=query, include_graph_context=True)
            elapsed = (time.perf_counter() - start) * 1000

            self.results['rag_with_context'].append(elapsed)

            # Check enrichment
            knowledge_context = result.get('knowledge_context', {})
            entities = knowledge_context.get('entity_count', 0)
            relationships = knowledge_context.get('relationship_count', 0)
            print(f"    Iteration {i+1}: {elapsed:.0f}ms (entities: {entities}, relationships: {relationships})")

        # Calculate overhead
        baseline_avg = mean(self.results['rag_no_context'])
        enriched_avg = mean(self.results['rag_with_context'])
        overhead = enriched_avg - baseline_avg

        print(f"\n  Baseline (no enrichment): {baseline_avg:.0f}ms")
        print(f"  Enriched (with context):  {enriched_avg:.0f}ms")
        print(f"  Overhead:                 {overhead:.0f}ms (target: <500ms)")
        print(f"  Total time target:        <10000ms")
        print(f"  Status: {'✅ PASS' if enriched_avg < 10000 and overhead < 500 else '⚠️  ABOVE TARGET'}")

    def _print_stats(self, key: str, target_ms: float):
        """Print statistics for a benchmark."""
        times = self.results[key]
        if not times:
            return

        avg = mean(times)
        med = median(times)
        std = stdev(times) if len(times) > 1 else 0
        min_time = min(times)
        max_time = max(times)

        print(f"\n  Statistics:")
        print(f"    Average: {avg:.0f}ms")
        print(f"    Median:  {med:.0f}ms")
        print(f"    StdDev:  {std:.0f}ms")
        print(f"    Min:     {min_time:.0f}ms")
        print(f"    Max:     {max_time:.0f}ms")
        print(f"    Target:  {target_ms:.0f}ms")
        print(f"    Status:  {'✅ PASS' if avg < target_ms else '⚠️  ABOVE TARGET'}")

    async def check_environment(self):
        """Check Neo4j connection and data state."""
        print("🔧 Checking environment...")

        # Check Neo4j connection
        client = await get_graphiti_client()
        is_available = await client.is_available()

        print(f"  Neo4j URI:     {os.getenv('NEO4J_URI', 'not set')}")
        print(f"  Neo4j status:  {'✅ Available' if is_available else '❌ Unavailable'}")

        if is_available:
            # Check data
            result = await knowledge_graph_search(query="test", limit=1)
            entity_count = len(result.get('entities', []))
            relationship_count = len(result.get('relationships', []))

            print(f"  Data state:    {entity_count} entities, {relationship_count} relationships")
            if entity_count == 0:
                print("  ⚠️  WARNING: No entities in graph. Benchmarks will test infrastructure only.")

        # Check txtai API
        txtai_url = os.getenv('TXTAI_API_URL', 'not set')
        print(f"  txtai API:     {txtai_url}")

        print()

    def print_summary(self):
        """Print summary of all benchmarks."""
        print("\n" + "=" * 80)
        print("PERFORMANCE BENCHMARK SUMMARY")
        print("=" * 80)

        summary = []

        # knowledge_graph_search
        if self.results['knowledge_graph_search']:
            avg = mean(self.results['knowledge_graph_search'])
            status = '✅ PASS' if avg < 2000 else '⚠️  ABOVE TARGET'
            summary.append(f"knowledge_graph_search:  {avg:6.0f}ms  (target: 2000ms)   {status}")

        # Search enrichment overhead
        if self.results['search_no_context'] and self.results['search_with_context']:
            baseline = mean(self.results['search_no_context'])
            enriched = mean(self.results['search_with_context'])
            overhead = enriched - baseline
            status = '✅ PASS' if overhead < 500 else '⚠️  ABOVE TARGET'
            summary.append(f"search enrichment:       {enriched:6.0f}ms  (overhead: {overhead:.0f}ms, target: <500ms) {status}")

        # RAG enrichment
        if self.results['rag_no_context'] and self.results['rag_with_context']:
            baseline = mean(self.results['rag_no_context'])
            enriched = mean(self.results['rag_with_context'])
            overhead = enriched - baseline
            status = '✅ PASS' if enriched < 10000 and overhead < 500 else '⚠️  ABOVE TARGET'
            summary.append(f"rag_query enrichment:    {enriched:6.0f}ms  (overhead: {overhead:.0f}ms, target: <500ms) {status}")

        for line in summary:
            print(line)

        print("\nNotes:")
        print("- These benchmarks test infrastructure and query paths")
        print("- With sparse/empty graph data, latencies reflect minimal processing")
        print("- Production performance with dense data may differ")
        print("- Target: knowledge_graph_search <2s, enrichment overhead <500ms, enriched RAG <10s")
        print("=" * 80)


async def main():
    """Run all benchmarks."""
    # Check required env vars
    required_vars = ['NEO4J_URI', 'NEO4J_PASSWORD', 'TXTAI_API_URL', 'TOGETHERAI_API_KEY']
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        print(f"❌ ERROR: Missing required environment variables: {', '.join(missing)}")
        print("\nSet these variables before running:")
        for var in missing:
            print(f"  export {var}=<value>")
        return 1

    benchmark = PerformanceBenchmark()

    # Check environment
    await benchmark.check_environment()

    # Run benchmarks with typical queries
    try:
        # Test 1: knowledge_graph_search (entity search)
        await benchmark.benchmark_knowledge_graph_search(
            query="machine learning",
            iterations=5
        )

        # Test 2: search enrichment (parallel query overhead)
        await benchmark.benchmark_search_enrichment(
            query="artificial intelligence",
            iterations=5
        )

        # Test 3: RAG enrichment (full workflow with LLM)
        await benchmark.benchmark_rag_enrichment(
            query="What is machine learning?",
            iterations=3  # Fewer iterations due to LLM cost
        )

        # Print summary
        benchmark.print_summary()

        return 0

    except Exception as e:
        print(f"\n❌ ERROR during benchmarking: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
