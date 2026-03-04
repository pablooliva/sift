#!/usr/bin/env python3
"""
Simplified performance benchmarking for SPEC-037.

Tests infrastructure and query paths with current data state.
"""

import asyncio
import os
import sys
import time
import httpx
from statistics import mean, median
from typing import List, Dict, Any

# Add to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from graphiti_integration.graphiti_client_async import GraphitiClientAsync


class SimpleBenchmark:
    """Simple performance tests."""

    def __init__(self):
        self.results = {}
        self.txtai_url = os.getenv('TXTAI_API_URL', 'http://localhost:8300')
        self.client = None

    async def setup(self):
        """Initialize Graphiti client."""
        self.client = GraphitiClientAsync(
            neo4j_uri=os.getenv('NEO4J_URI'),
            neo4j_user=os.getenv('NEO4J_USER', 'neo4j'),
            neo4j_password=os.getenv('NEO4J_PASSWORD'),
            together_api_key=os.getenv('TOGETHERAI_API_KEY', ''),
            ollama_api_url=os.getenv('OLLAMA_API_URL', 'http://localhost:11434')
        )
        # Graphiti client initializes lazily, no explicit initialize() needed

    async def cleanup(self):
        """Cleanup resources."""
        if self.client:
            await self.client.close()

    async def benchmark_knowledge_graph_search(self, iterations=5):
        """Benchmark Graphiti search directly."""
        print(f"\n🔍 Benchmarking knowledge_graph_search ({iterations} iterations)...")

        times = []
        query = "machine learning"

        for i in range(iterations):
            start = time.perf_counter()

            # Direct Graphiti search
            result = await self.client.search(
                query=query,
                limit=15
            )

            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

            entities = len(result.get('entities', []))
            relationships = len(result.get('relationships', []))
            print(f"  Iteration {i+1}: {elapsed:.0f}ms (entities: {entities}, relationships: {relationships})")

        self.results['knowledge_graph_search'] = times
        self._print_stats('knowledge_graph_search', times, target_ms=2000)

    async def benchmark_search_parallel(self, iterations=5):
        """Benchmark parallel txtai + Graphiti search."""
        print(f"\n📄 Benchmarking parallel search overhead ({iterations} iterations)...")

        times_baseline = []
        times_parallel = []
        query = "artificial intelligence"

        # Baseline: txtai only
        print("  Baseline (txtai only):")
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            for i in range(iterations):
                start = time.perf_counter()

                response = await http_client.get(
                    f"{self.txtai_url}/search",
                    params={"query": query, "limit": 10}
                )

                elapsed = (time.perf_counter() - start) * 1000
                times_baseline.append(elapsed)

                results = response.json() if response.status_code == 200 else []
                print(f"    Iteration {i+1}: {elapsed:.0f}ms (results: {len(results)})")

        # Parallel: txtai + Graphiti
        print("  Parallel (txtai + Graphiti):")
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            for i in range(iterations):
                start = time.perf_counter()

                # Simulate parallel queries
                txtai_task = http_client.get(
                    f"{self.txtai_url}/search",
                    params={"query": query, "limit": 10}
                )
                graphiti_task = self.client.search(query=query, limit=15)

                txtai_result, graphiti_result = await asyncio.gather(txtai_task, graphiti_task)

                elapsed = (time.perf_counter() - start) * 1000
                times_parallel.append(elapsed)

                print(f"    Iteration {i+1}: {elapsed:.0f}ms")

        self.results['search_baseline'] = times_baseline
        self.results['search_parallel'] = times_parallel

        # Calculate overhead
        baseline_avg = mean(times_baseline)
        parallel_avg = mean(times_parallel)
        overhead = parallel_avg - baseline_avg

        print(f"\n  Baseline average:  {baseline_avg:.0f}ms")
        print(f"  Parallel average:  {parallel_avg:.0f}ms")
        print(f"  Overhead:          {overhead:.0f}ms (target: <500ms)")
        print(f"  Status:            {'✅ PASS' if overhead < 500 else '⚠️  ABOVE TARGET'}")

    def _print_stats(self, name: str, times: List[float], target_ms: float):
        """Print statistics."""
        if not times:
            return

        avg = mean(times)
        med = median(times)
        min_t = min(times)
        max_t = max(times)

        print(f"\n  Statistics:")
        print(f"    Average:  {avg:.0f}ms")
        print(f"    Median:   {med:.0f}ms")
        print(f"    Min:      {min_t:.0f}ms")
        print(f"    Max:      {max_t:.0f}ms")
        print(f"    Target:   {target_ms:.0f}ms")
        print(f"    Status:   {'✅ PASS' if avg < target_ms else '⚠️  ABOVE TARGET'}")

    async def check_environment(self):
        """Check environment and data state."""
        print("🔧 Checking environment...")
        print(f"  Neo4j URI:     {os.getenv('NEO4J_URI', 'not set')}")
        print(f"  txtai API:     {self.txtai_url}")

        # Check Neo4j connection
        is_available = await self.client.is_available()
        print(f"  Neo4j status:  {'✅ Available' if is_available else '❌ Unavailable'}")

        if is_available:
            # Check data
            result = await self.client.search(query="test", limit=1)
            entity_count = len(result.get('entities', []))
            relationship_count = len(result.get('relationships', []))

            print(f"  Data state:    {entity_count} entities, {relationship_count} relationships")
            if entity_count == 0:
                print("  ⚠️  WARNING: Empty graph. Benchmarks test infrastructure only.")

        # Check txtai API
        try:
            async with httpx.AsyncClient(timeout=5.0) as http_client:
                response = await http_client.get(f"{self.txtai_url}/count")
                if response.status_code == 200:
                    count = response.json()
                    print(f"  txtai docs:    {count}")
                else:
                    print(f"  txtai API:     ❌ Error (status {response.status_code})")
        except Exception as e:
            print(f"  txtai API:     ❌ Error ({e})")

        print()

    def print_summary(self):
        """Print final summary."""
        print("\n" + "=" * 80)
        print("PERFORMANCE BENCHMARK SUMMARY")
        print("=" * 80)

        if 'knowledge_graph_search' in self.results:
            avg = mean(self.results['knowledge_graph_search'])
            status = '✅ PASS' if avg < 2000 else '⚠️  ABOVE TARGET'
            print(f"knowledge_graph_search:  {avg:6.0f}ms  (target: <2000ms)  {status}")

        if 'search_baseline' in self.results and 'search_parallel' in self.results:
            baseline = mean(self.results['search_baseline'])
            parallel = mean(self.results['search_parallel'])
            overhead = parallel - baseline
            status = '✅ PASS' if overhead < 500 else '⚠️  ABOVE TARGET'
            print(f"search parallel overhead: {overhead:6.0f}ms  (target: <500ms)   {status}")

        print("\nNotes:")
        print("- Benchmarks test infrastructure with current data state")
        print("- Empty/sparse graph = minimal processing latency")
        print("- Production performance may differ with dense data")
        print("- Targets: knowledge_graph_search <2s, parallel overhead <500ms")
        print("=" * 80)


async def main():
    """Run benchmarks."""
    # Check env vars
    required = ['NEO4J_URI', 'NEO4J_PASSWORD', 'TXTAI_API_URL', 'TOGETHERAI_API_KEY']
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        print(f"❌ Missing env vars: {', '.join(missing)}")
        return 1

    benchmark = SimpleBenchmark()

    try:
        await benchmark.setup()
        await benchmark.check_environment()

        # Run benchmarks
        await benchmark.benchmark_knowledge_graph_search(iterations=5)
        await benchmark.benchmark_search_parallel(iterations=5)

        benchmark.print_summary()

        return 0

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        await benchmark.cleanup()


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
