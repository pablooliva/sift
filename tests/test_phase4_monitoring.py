"""
Phase 4 Testing: Monitoring and Optimization (SPEC-013)

Tests for usage metrics tracking, performance monitoring, and quality tracking.

Test Coverage:
- Monitoring module functionality
- Query logging (start, end, fallback)
- Metrics calculation and aggregation
- Query history retrieval
- Privacy-aware logging
- Dashboard script functionality
"""

import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add project root to path (parent.parent goes from tests/ to project root)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import monitoring module directly to avoid streamlit dependencies
import importlib.util
spec = importlib.util.spec_from_file_location(
    "monitoring",
    project_root / "frontend" / "utils" / "monitoring.py"
)
monitoring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitoring)
QueryMonitor = monitoring.QueryMonitor


class TestPhase4Monitoring(unittest.TestCase):
    """Test Phase 4 monitoring and metrics tracking."""

    def setUp(self):
        """Set up test environment with temporary log directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.monitor = QueryMonitor(log_dir=self.temp_dir)

    def tearDown(self):
        """Clean up temporary log files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ===== Test Suite 1: Basic Logging =====

    def test_log_query_start(self):
        """TEST-MON-001: Log query start with privacy-aware hashing."""
        query_id = self.monitor.log_query_start(
            question="What documents do I have?",
            route="rag",
            log_question_text=False
        )

        # Verify query_id is returned
        self.assertIsNotNone(query_id)
        self.assertIsInstance(query_id, str)

        # Verify log file created
        self.assertTrue(self.monitor.current_log_file.exists())

        # Verify log entry (without full question text for privacy)
        with open(self.monitor.current_log_file, 'r') as f:
            entry = json.loads(f.readline())
            self.assertEqual(entry["event"], "query_start")
            self.assertEqual(entry["route"], "rag")
            self.assertEqual(entry["question_length"], 25)
            self.assertIn("question_hash", entry)
            self.assertNotIn("question", entry)  # Privacy: not logged

    def test_log_query_start_with_question_text(self):
        """TEST-MON-002: Log query start with full question text when enabled."""
        query_id = self.monitor.log_query_start(
            question="Test question",
            route="manual",
            log_question_text=True
        )

        # Verify log entry includes full question
        with open(self.monitor.current_log_file, 'r') as f:
            entry = json.loads(f.readline())
            self.assertIn("question", entry)
            self.assertEqual(entry["question"], "Test question")

    def test_log_query_end(self):
        """TEST-MON-003: Log query completion with metrics."""
        query_id = self.monitor.log_query_start("Test", "rag")

        self.monitor.log_query_end(
            query_id=query_id,
            success=True,
            response_time=7.2,
            num_sources=5,
            fallback_reason=None
        )

        # Verify both entries logged
        with open(self.monitor.current_log_file, 'r') as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 2)

            start_entry = json.loads(lines[0])
            end_entry = json.loads(lines[1])

            self.assertEqual(start_entry["event"], "query_start")
            self.assertEqual(end_entry["event"], "query_end")
            self.assertEqual(end_entry["success"], True)
            self.assertEqual(end_entry["response_time"], 7.2)
            self.assertEqual(end_entry["num_sources"], 5)

    def test_log_fallback(self):
        """TEST-MON-004: Log fallback from RAG to manual."""
        query_id = self.monitor.log_query_start("Test", "rag")

        self.monitor.log_fallback(
            query_id=query_id,
            from_route="rag",
            to_route="manual",
            reason="timeout"
        )

        # Verify fallback logged
        with open(self.monitor.current_log_file, 'r') as f:
            lines = f.readlines()
            fallback_entry = json.loads(lines[1])

            self.assertEqual(fallback_entry["event"], "fallback")
            self.assertEqual(fallback_entry["from_route"], "rag")
            self.assertEqual(fallback_entry["to_route"], "manual")
            self.assertEqual(fallback_entry["reason"], "timeout")

    def test_log_quality_feedback(self):
        """TEST-MON-005: Log user quality feedback."""
        query_id = self.monitor.log_query_start("Test", "rag")

        self.monitor.log_quality_feedback(
            query_id=query_id,
            helpful=True,
            comment="Great answer!"
        )

        # Verify feedback logged
        with open(self.monitor.current_log_file, 'r') as f:
            lines = f.readlines()
            feedback_entry = json.loads(lines[1])

            self.assertEqual(feedback_entry["event"], "quality_feedback")
            self.assertEqual(feedback_entry["helpful"], True)
            self.assertEqual(feedback_entry["comment"], "Great answer!")

    # ===== Test Suite 2: Metrics Calculation =====

    def test_get_metrics_empty(self):
        """TEST-MON-006: Get metrics when no queries logged."""
        metrics = self.monitor.get_metrics(days=7)

        self.assertEqual(metrics["total_queries"], 0)
        self.assertEqual(metrics["usage"]["rag_queries"], 0)
        self.assertEqual(metrics["usage"]["manual_queries"], 0)

    def test_get_metrics_single_rag_query(self):
        """TEST-MON-007: Get metrics for single RAG query."""
        query_id = self.monitor.log_query_start("Test question?", "rag")
        self.monitor.log_query_end(query_id, True, 7.5, 5)

        metrics = self.monitor.get_metrics(days=7)

        self.assertEqual(metrics["total_queries"], 1)
        self.assertEqual(metrics["usage"]["rag_queries"], 1)
        self.assertEqual(metrics["usage"]["manual_queries"], 0)
        self.assertEqual(metrics["usage"]["rag_percentage"], 100.0)
        self.assertEqual(metrics["quality"]["successful_queries"], 1)
        self.assertEqual(metrics["quality"]["success_rate"], 100.0)
        self.assertAlmostEqual(metrics["performance"]["avg_response_time"], 7.5)

    def test_get_metrics_multiple_queries(self):
        """TEST-MON-008: Get metrics for multiple queries with different routes."""
        # RAG query 1
        q1 = self.monitor.log_query_start("Q1", "rag")
        self.monitor.log_query_end(q1, True, 6.0, 3)

        # RAG query 2
        q2 = self.monitor.log_query_start("Q2", "rag")
        self.monitor.log_query_end(q2, True, 8.0, 5)

        # Manual query
        q3 = self.monitor.log_query_start("Q3", "manual")
        self.monitor.log_query_end(q3, True, 45.0, 0)

        metrics = self.monitor.get_metrics(days=7)

        self.assertEqual(metrics["total_queries"], 3)
        self.assertEqual(metrics["usage"]["rag_queries"], 2)
        self.assertEqual(metrics["usage"]["manual_queries"], 1)
        self.assertAlmostEqual(metrics["usage"]["rag_percentage"], 66.67, places=1)
        self.assertAlmostEqual(metrics["performance"]["avg_rag_time"], 7.0)

    def test_get_metrics_with_fallbacks(self):
        """TEST-MON-009: Get metrics with fallback tracking."""
        # Query with timeout fallback
        q1 = self.monitor.log_query_start("Q1", "rag")
        self.monitor.log_fallback(q1, "rag", "manual", "timeout")
        self.monitor.log_query_end(q1, True, 60.0, 0)

        # Query with quality fallback
        q2 = self.monitor.log_query_start("Q2", "rag")
        self.monitor.log_fallback(q2, "rag", "manual", "quality")
        self.monitor.log_query_end(q2, True, 50.0, 0)

        # Successful RAG query
        q3 = self.monitor.log_query_start("Q3", "rag")
        self.monitor.log_query_end(q3, True, 7.0, 5)

        metrics = self.monitor.get_metrics(days=7)

        self.assertEqual(metrics["quality"]["fallbacks"], 2)
        self.assertAlmostEqual(metrics["quality"]["fallback_rate"], 66.67, places=1)
        self.assertEqual(metrics["quality"]["fallback_reasons"]["timeout"], 1)
        self.assertEqual(metrics["quality"]["fallback_reasons"]["quality"], 1)

    def test_get_metrics_with_failures(self):
        """TEST-MON-010: Get metrics with failed queries."""
        # Successful query
        q1 = self.monitor.log_query_start("Q1", "rag")
        self.monitor.log_query_end(q1, True, 7.0, 5)

        # Failed query
        q2 = self.monitor.log_query_start("Q2", "rag")
        self.monitor.log_query_end(q2, False, 0, 0)

        metrics = self.monitor.get_metrics(days=7)

        self.assertEqual(metrics["quality"]["successful_queries"], 1)
        self.assertEqual(metrics["quality"]["failed_queries"], 1)
        self.assertEqual(metrics["quality"]["success_rate"], 50.0)

    def test_get_metrics_with_feedback(self):
        """TEST-MON-011: Get metrics with user feedback."""
        # Query 1: Helpful
        q1 = self.monitor.log_query_start("Q1", "rag")
        self.monitor.log_query_end(q1, True, 7.0, 5)
        self.monitor.log_quality_feedback(q1, helpful=True)

        # Query 2: Not helpful
        q2 = self.monitor.log_query_start("Q2", "rag")
        self.monitor.log_query_end(q2, True, 7.0, 5)
        self.monitor.log_quality_feedback(q2, helpful=False)

        # Query 3: Helpful
        q3 = self.monitor.log_query_start("Q3", "rag")
        self.monitor.log_query_end(q3, True, 7.0, 5)
        self.monitor.log_quality_feedback(q3, helpful=True)

        metrics = self.monitor.get_metrics(days=7)

        self.assertEqual(metrics["feedback"]["total_feedback"], 3)
        self.assertEqual(metrics["feedback"]["helpful"], 2)
        self.assertEqual(metrics["feedback"]["unhelpful"], 1)
        self.assertAlmostEqual(metrics["feedback"]["satisfaction_rate"], 66.67, places=1)

    # ===== Test Suite 3: Query History =====

    def test_get_query_history(self):
        """TEST-MON-012: Get query history with complete information."""
        q1 = self.monitor.log_query_start("Test 1", "rag", log_question_text=True)
        self.monitor.log_query_end(q1, True, 7.0, 5)

        q2 = self.monitor.log_query_start("Test 2", "manual", log_question_text=True)
        self.monitor.log_query_end(q2, True, 45.0, 0)

        history = self.monitor.get_query_history(days=7, include_question_text=True)

        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["route"], "manual")  # Sorted newest first
        self.assertEqual(history[0]["question"], "Test 2")
        self.assertEqual(history[1]["route"], "rag")
        self.assertEqual(history[1]["question"], "Test 1")

    def test_get_query_history_filter_by_route(self):
        """TEST-MON-013: Get query history filtered by route."""
        q1 = self.monitor.log_query_start("Q1", "rag")
        self.monitor.log_query_end(q1, True, 7.0, 5)

        q2 = self.monitor.log_query_start("Q2", "manual")
        self.monitor.log_query_end(q2, True, 45.0, 0)

        q3 = self.monitor.log_query_start("Q3", "rag")
        self.monitor.log_query_end(q3, True, 6.0, 3)

        # Filter for RAG only
        rag_history = self.monitor.get_query_history(days=7, route="rag")
        self.assertEqual(len(rag_history), 2)
        self.assertTrue(all(q["route"] == "rag" for q in rag_history))

        # Filter for manual only
        manual_history = self.monitor.get_query_history(days=7, route="manual")
        self.assertEqual(len(manual_history), 1)
        self.assertEqual(manual_history[0]["route"], "manual")

    def test_get_query_history_with_fallback(self):
        """TEST-MON-014: Get query history shows fallback information."""
        q1 = self.monitor.log_query_start("Q1", "rag")
        self.monitor.log_fallback(q1, "rag", "manual", "timeout")
        self.monitor.log_query_end(q1, True, 60.0, 0)

        history = self.monitor.get_query_history(days=7)

        self.assertEqual(len(history), 1)
        self.assertTrue(history[0]["had_fallback"])
        self.assertEqual(history[0]["fallback_reason"], "timeout")

    # ===== Test Suite 4: Multi-Day Logging =====

    def test_multiple_log_files_by_date(self):
        """TEST-MON-015: Verify log files created by date."""
        # Log a query
        q1 = self.monitor.log_query_start("Q1", "rag")
        self.monitor.log_query_end(q1, True, 7.0, 5)

        # Verify today's log file exists
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = Path(self.temp_dir) / f"{today}.jsonl"
        self.assertTrue(log_file.exists())

    def test_metrics_days_filter(self):
        """TEST-MON-016: Verify metrics respect days filter."""
        # This would require mocking datetime or manipulating file timestamps
        # For now, basic test that filter works
        q1 = self.monitor.log_query_start("Q1", "rag")
        self.monitor.log_query_end(q1, True, 7.0, 5)

        metrics_7d = self.monitor.get_metrics(days=7)
        metrics_1d = self.monitor.get_metrics(days=1)

        # Both should include today's query
        self.assertEqual(metrics_7d["total_queries"], 1)
        self.assertEqual(metrics_1d["total_queries"], 1)

    # ===== Test Suite 5: Edge Cases =====

    def test_logging_failure_doesnt_crash(self):
        """TEST-MON-017: Logging failures don't crash (graceful degradation)."""
        # Create a valid monitor first, then break the log file
        # to simulate write failure
        q1 = self.monitor.log_query_start("Test", "rag")

        # Make log file unwritable by chmod
        import stat
        self.monitor.current_log_file.chmod(stat.S_IRUSR)  # Read-only

        # Should not raise exception when logging fails
        try:
            self.monitor.log_query_end(q1, True, 7.0, 5)
            # Logging fails silently (prints warning but doesn't crash)
        except Exception as e:
            self.fail(f"Logging failure should not crash: {e}")
        finally:
            # Restore permissions for cleanup
            try:
                self.monitor.current_log_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
            except:
                pass

    def test_incomplete_query_handling(self):
        """TEST-MON-018: Handle incomplete queries (start without end)."""
        q1 = self.monitor.log_query_start("Q1", "rag")
        # Intentionally don't call log_query_end

        q2 = self.monitor.log_query_start("Q2", "rag")
        self.monitor.log_query_end(q2, True, 7.0, 5)

        metrics = self.monitor.get_metrics(days=7)

        # Should count both queries, but only Q2 as successful
        self.assertEqual(metrics["total_queries"], 2)
        self.assertEqual(metrics["quality"]["successful_queries"], 1)

    def test_concurrent_query_ids_unique(self):
        """TEST-MON-019: Concurrent queries get unique IDs."""
        q1 = self.monitor.log_query_start("Q1", "rag")
        q2 = self.monitor.log_query_start("Q2", "rag")
        q3 = self.monitor.log_query_start("Q3", "manual")

        # All IDs should be unique
        ids = [q1, q2, q3]
        self.assertEqual(len(ids), len(set(ids)))

    # ===== Test Suite 6: Performance =====

    def test_logging_performance(self):
        """TEST-MON-020: Verify logging is fast (non-blocking)."""
        start_time = time.time()

        # Log 100 queries
        for i in range(100):
            q = self.monitor.log_query_start(f"Q{i}", "rag")
            self.monitor.log_query_end(q, True, 7.0, 5)

        elapsed = time.time() - start_time

        # Should complete in < 1 second (very generous)
        self.assertLess(elapsed, 1.0, "Logging 100 queries should be fast")

    def test_metrics_calculation_performance(self):
        """TEST-MON-021: Verify metrics calculation is fast."""
        # Log 1000 queries
        for i in range(1000):
            q = self.monitor.log_query_start(f"Q{i}", "rag" if i % 2 == 0 else "manual")
            self.monitor.log_query_end(q, True, 7.0, 5)

        start_time = time.time()
        metrics = self.monitor.get_metrics(days=7)
        elapsed = time.time() - start_time

        # Should complete in < 2 seconds
        self.assertLess(elapsed, 2.0, "Metrics calculation for 1000 queries should be fast")
        self.assertEqual(metrics["total_queries"], 1000)


def run_tests():
    """Run all Phase 4 monitoring tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestPhase4Monitoring)

    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "=" * 70)
    print("PHASE 4 MONITORING TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("=" * 70)

    if result.wasSuccessful():
        print("✅ ALL PHASE 4 TESTS PASSED")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
