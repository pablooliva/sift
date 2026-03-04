"""
Monitoring and Metrics Tracking for SPEC-013 Phase 4

Tracks usage metrics, performance, and quality for the RAG + Manual hybrid system.

Features:
- Query logging (route, response time, success)
- Usage metrics (RAG vs manual counts)
- Quality tracking (fallback reasons, success rates)
- Performance monitoring (response times, timeouts)
- Privacy-aware (configurable query text logging)

Usage:
    from frontend.utils.monitoring import QueryMonitor

    monitor = QueryMonitor()

    # Log a query start
    query_id = monitor.log_query_start(
        question="What documents do I have?",
        route="rag",
        log_question_text=False  # Privacy setting
    )

    # Log query completion
    monitor.log_query_end(
        query_id=query_id,
        success=True,
        response_time=7.2,
        num_sources=5,
        fallback_reason=None
    )

    # Get metrics
    metrics = monitor.get_metrics(days=7)
"""

import json
import os
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any


class QueryMonitor:
    """Monitor and track RAG query usage and performance."""

    def __init__(self, log_dir: Optional[str] = None):
        """
        Initialize the query monitor.

        Args:
            log_dir: Directory to store logs. Defaults to 'logs/monitoring/' in project root.
        """
        if log_dir is None:
            # Default to logs/monitoring/ relative to project root
            project_root = Path(__file__).parent.parent.parent
            log_dir = project_root / "logs" / "monitoring"

        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Current log file (YYYY-MM-DD.jsonl format)
        self.current_log_file = self.log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"

    def log_query_start(
        self,
        question: str,
        route: str,
        log_question_text: bool = False
    ) -> str:
        """
        Log the start of a query.

        Args:
            question: The user's question
            route: Routing decision ('rag' or 'manual')
            log_question_text: Whether to log the full question (privacy setting)

        Returns:
            query_id: Unique identifier for this query
        """
        query_id = str(uuid.uuid4())

        log_entry = {
            "query_id": query_id,
            "timestamp": datetime.now().isoformat(),
            "event": "query_start",
            "route": route,
            "question_length": len(question),
            "question_hash": hash(question) % 10000,  # Privacy-safe identifier
        }

        # Only log full question if explicitly enabled
        if log_question_text:
            log_entry["question"] = question

        self._write_log_entry(log_entry)
        return query_id

    def log_query_end(
        self,
        query_id: str,
        success: bool,
        response_time: float,
        num_sources: int = 0,
        fallback_reason: Optional[str] = None,
        quality_score: Optional[float] = None
    ):
        """
        Log the completion of a query.

        Args:
            query_id: Unique identifier from log_query_start
            success: Whether the query succeeded
            response_time: Time taken in seconds
            num_sources: Number of source documents used
            fallback_reason: Reason for fallback (if any): 'timeout', 'error', 'quality'
            quality_score: Optional quality score (0-1)
        """
        log_entry = {
            "query_id": query_id,
            "timestamp": datetime.now().isoformat(),
            "event": "query_end",
            "success": success,
            "response_time": response_time,
            "num_sources": num_sources,
            "fallback_reason": fallback_reason,
            "quality_score": quality_score
        }

        self._write_log_entry(log_entry)

    def log_fallback(
        self,
        query_id: str,
        from_route: str,
        to_route: str,
        reason: str
    ):
        """
        Log a fallback from one route to another.

        Args:
            query_id: Unique identifier for the query
            from_route: Original route ('rag')
            to_route: Fallback route ('manual')
            reason: Reason for fallback: 'timeout', 'error', 'quality', 'no_results'
        """
        log_entry = {
            "query_id": query_id,
            "timestamp": datetime.now().isoformat(),
            "event": "fallback",
            "from_route": from_route,
            "to_route": to_route,
            "reason": reason
        }

        self._write_log_entry(log_entry)

    def log_quality_feedback(
        self,
        query_id: str,
        helpful: bool,
        comment: Optional[str] = None
    ):
        """
        Log user feedback on query quality.

        Args:
            query_id: Unique identifier for the query
            helpful: Whether the user found the answer helpful
            comment: Optional user comment
        """
        log_entry = {
            "query_id": query_id,
            "timestamp": datetime.now().isoformat(),
            "event": "quality_feedback",
            "helpful": helpful,
            "comment": comment
        }

        self._write_log_entry(log_entry)

    def _write_log_entry(self, entry: Dict[str, Any]):
        """Write a log entry to the current log file (JSONL format)."""
        try:
            with open(self.current_log_file, 'a') as f:
                json.dump(entry, f)
                f.write('\n')
        except Exception as e:
            # Don't fail queries if logging fails
            print(f"Warning: Failed to write monitoring log: {e}")

    def _read_log_entries(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Read log entries from the last N days.

        Args:
            days: Number of days to look back

        Returns:
            List of log entries
        """
        entries = []
        cutoff_date = datetime.now() - timedelta(days=days)

        # Read all log files within the date range
        for log_file in sorted(self.log_dir.glob("*.jsonl")):
            try:
                # Parse date from filename (YYYY-MM-DD.jsonl)
                file_date_str = log_file.stem
                file_date = datetime.strptime(file_date_str, "%Y-%m-%d")

                if file_date >= cutoff_date:
                    with open(log_file, 'r') as f:
                        for line in f:
                            if line.strip():
                                entries.append(json.loads(line))
            except Exception as e:
                print(f"Warning: Failed to read log file {log_file}: {e}")

        return entries

    def get_metrics(self, days: int = 7) -> Dict[str, Any]:
        """
        Get aggregated metrics for the last N days.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary of metrics
        """
        entries = self._read_log_entries(days)

        # Group entries by query_id
        queries = {}
        for entry in entries:
            query_id = entry.get("query_id")
            if query_id:
                if query_id not in queries:
                    queries[query_id] = {}
                queries[query_id][entry["event"]] = entry

        # Calculate metrics
        total_queries = len(queries)
        rag_queries = sum(1 for q in queries.values() if q.get("query_start", {}).get("route") == "rag")
        manual_queries = sum(1 for q in queries.values() if q.get("query_start", {}).get("route") == "manual")

        successful_queries = sum(1 for q in queries.values() if q.get("query_end", {}).get("success", False))
        failed_queries = total_queries - successful_queries

        fallbacks = sum(1 for q in queries.values() if "fallback" in q)

        # Response time statistics (only for successful queries)
        response_times = [
            q["query_end"]["response_time"]
            for q in queries.values()
            if "query_end" in q and q["query_end"].get("success", False)
        ]

        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        min_response_time = min(response_times) if response_times else 0
        max_response_time = max(response_times) if response_times else 0

        # RAG-specific metrics
        rag_response_times = [
            q["query_end"]["response_time"]
            for q in queries.values()
            if q.get("query_start", {}).get("route") == "rag"
            and "query_end" in q
            and q["query_end"].get("success", False)
        ]
        avg_rag_time = sum(rag_response_times) / len(rag_response_times) if rag_response_times else 0

        # Fallback reasons
        fallback_reasons = {}
        for q in queries.values():
            if "fallback" in q:
                reason = q["fallback"].get("reason", "unknown")
                fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1

        # Quality feedback
        feedback_entries = [q.get("quality_feedback") for q in queries.values() if "quality_feedback" in q]
        helpful_count = sum(1 for f in feedback_entries if f and f.get("helpful", False))
        unhelpful_count = sum(1 for f in feedback_entries if f and not f.get("helpful", False))

        return {
            "period_days": days,
            "total_queries": total_queries,
            "usage": {
                "rag_queries": rag_queries,
                "manual_queries": manual_queries,
                "rag_percentage": (rag_queries / total_queries * 100) if total_queries > 0 else 0
            },
            "performance": {
                "avg_response_time": avg_response_time,
                "min_response_time": min_response_time,
                "max_response_time": max_response_time,
                "avg_rag_time": avg_rag_time
            },
            "quality": {
                "successful_queries": successful_queries,
                "failed_queries": failed_queries,
                "success_rate": (successful_queries / total_queries * 100) if total_queries > 0 else 0,
                "fallbacks": fallbacks,
                "fallback_rate": (fallbacks / total_queries * 100) if total_queries > 0 else 0,
                "fallback_reasons": fallback_reasons
            },
            "feedback": {
                "total_feedback": len(feedback_entries),
                "helpful": helpful_count,
                "unhelpful": unhelpful_count,
                "satisfaction_rate": (helpful_count / len(feedback_entries) * 100) if feedback_entries else 0
            }
        }

    def get_query_history(
        self,
        days: int = 7,
        route: Optional[str] = None,
        include_question_text: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get query history for analysis.

        Args:
            days: Number of days to look back
            route: Filter by route ('rag', 'manual', or None for all)
            include_question_text: Include full question text if logged

        Returns:
            List of query records with start and end data merged
        """
        entries = self._read_log_entries(days)

        # Group by query_id
        queries = {}
        for entry in entries:
            query_id = entry.get("query_id")
            if query_id:
                if query_id not in queries:
                    queries[query_id] = {}
                queries[query_id][entry["event"]] = entry

        # Build query history
        history = []
        for query_id, events in queries.items():
            if "query_start" not in events:
                continue

            start = events["query_start"]
            end = events.get("query_end", {})
            fallback = events.get("fallback")

            # Filter by route if specified
            if route and start.get("route") != route:
                continue

            record = {
                "query_id": query_id,
                "timestamp": start.get("timestamp"),
                "route": start.get("route"),
                "question_length": start.get("question_length"),
                "success": end.get("success"),
                "response_time": end.get("response_time"),
                "num_sources": end.get("num_sources"),
                "had_fallback": fallback is not None,
                "fallback_reason": fallback.get("reason") if fallback else None
            }

            if include_question_text and "question" in start:
                record["question"] = start["question"]

            history.append(record)

        # Sort by timestamp (newest first)
        history.sort(key=lambda x: x["timestamp"], reverse=True)

        return history


# Singleton instance for easy access
_default_monitor = None

def get_monitor() -> QueryMonitor:
    """Get the default QueryMonitor instance."""
    global _default_monitor
    if _default_monitor is None:
        _default_monitor = QueryMonitor()
    return _default_monitor
