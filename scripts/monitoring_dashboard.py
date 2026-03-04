#!/usr/bin/env python3
"""
Monitoring Dashboard and Report Generation for SPEC-013 Phase 4

Generates reports and visualizations of RAG + Manual hybrid system usage.

Usage:
    # Generate text report for last 7 days
    python scripts/monitoring_dashboard.py

    # Generate report for last 30 days
    python scripts/monitoring_dashboard.py --days 30

    # Export metrics to JSON
    python scripts/monitoring_dashboard.py --format json --output metrics.json

    # Show query history
    python scripts/monitoring_dashboard.py --history

Features:
- Usage metrics (RAG vs manual distribution)
- Performance statistics (response times, timeouts)
- Quality metrics (success rates, fallback frequency)
- Query history and analysis
- Trend detection (if sufficient data)
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from frontend.utils.monitoring import QueryMonitor


def format_metrics_text(metrics: Dict[str, Any]) -> str:
    """Format metrics as human-readable text report."""

    report = []
    report.append("=" * 70)
    report.append("RAG + Manual Hybrid System - Monitoring Report")
    report.append("=" * 70)
    report.append(f"Period: Last {metrics['period_days']} days")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")

    # Usage Metrics
    report.append("USAGE METRICS")
    report.append("-" * 70)
    report.append(f"Total Queries: {metrics['total_queries']}")
    report.append(f"  - RAG Queries: {metrics['usage']['rag_queries']} ({metrics['usage']['rag_percentage']:.1f}%)")
    report.append(f"  - Manual Queries: {metrics['usage']['manual_queries']} ({100 - metrics['usage']['rag_percentage']:.1f}%)")
    report.append("")

    # Performance Metrics
    report.append("PERFORMANCE METRICS")
    report.append("-" * 70)
    if metrics['performance']['avg_response_time'] > 0:
        report.append(f"Response Times:")
        report.append(f"  - Average: {metrics['performance']['avg_response_time']:.2f}s")
        report.append(f"  - Min: {metrics['performance']['min_response_time']:.2f}s")
        report.append(f"  - Max: {metrics['performance']['max_response_time']:.2f}s")
        if metrics['performance']['avg_rag_time'] > 0:
            report.append(f"  - RAG Average: {metrics['performance']['avg_rag_time']:.2f}s")
            if metrics['performance']['avg_rag_time'] > 5.0:
                report.append(f"    ⚠️  RAG queries exceeding 5s target")
    else:
        report.append("No completed queries to analyze")
    report.append("")

    # Quality Metrics
    report.append("QUALITY METRICS")
    report.append("-" * 70)
    report.append(f"Success Rate: {metrics['quality']['success_rate']:.1f}%")
    report.append(f"  - Successful: {metrics['quality']['successful_queries']}")
    report.append(f"  - Failed: {metrics['quality']['failed_queries']}")
    report.append("")
    report.append(f"Fallback Rate: {metrics['quality']['fallback_rate']:.1f}%")
    report.append(f"  - Total Fallbacks: {metrics['quality']['fallbacks']}")

    if metrics['quality']['fallback_reasons']:
        report.append(f"  - Fallback Reasons:")
        for reason, count in metrics['quality']['fallback_reasons'].items():
            report.append(f"    - {reason}: {count}")
    report.append("")

    # Feedback Metrics
    report.append("USER FEEDBACK")
    report.append("-" * 70)
    if metrics['feedback']['total_feedback'] > 0:
        report.append(f"Total Feedback: {metrics['feedback']['total_feedback']}")
        report.append(f"  - Helpful: {metrics['feedback']['helpful']}")
        report.append(f"  - Not Helpful: {metrics['feedback']['unhelpful']}")
        report.append(f"  - Satisfaction: {metrics['feedback']['satisfaction_rate']:.1f}%")
    else:
        report.append("No user feedback collected yet")
    report.append("")

    # Insights and Recommendations
    report.append("INSIGHTS & RECOMMENDATIONS")
    report.append("-" * 70)

    insights = []

    # RAG usage analysis
    if metrics['total_queries'] > 0:
        rag_pct = metrics['usage']['rag_percentage']
        if rag_pct < 20:
            insights.append("⚠️  Low RAG usage (<20%). Consider reviewing routing logic.")
        elif rag_pct > 80:
            insights.append("✓ High RAG usage (>80%). System effectively routing simple queries.")
        else:
            insights.append(f"✓ Balanced routing: {rag_pct:.0f}% RAG, {100-rag_pct:.0f}% manual.")

    # Performance analysis
    if metrics['performance']['avg_rag_time'] > 5.0:
        insights.append("⚠️  RAG response time exceeds 5s target. Consider optimization.")
    elif metrics['performance']['avg_rag_time'] > 0:
        insights.append("✓ RAG response times within acceptable range (<5s).")

    # Quality analysis
    success_rate = metrics['quality']['success_rate']
    if success_rate < 80:
        insights.append("⚠️  Success rate below 80%. Review failure causes.")
    elif success_rate > 95:
        insights.append("✓ Excellent success rate (>95%).")

    # Fallback analysis
    fallback_rate = metrics['quality']['fallback_rate']
    if fallback_rate > 30:
        insights.append("⚠️  High fallback rate (>30%). RAG may need tuning.")
    elif fallback_rate > 0:
        insights.append(f"✓ Fallback rate reasonable ({fallback_rate:.0f}%).")

    # Feedback analysis
    if metrics['feedback']['total_feedback'] < metrics['total_queries'] * 0.1:
        insights.append("💡 Low feedback collection. Consider adding feedback prompts.")
    elif metrics['feedback']['satisfaction_rate'] < 70:
        insights.append("⚠️  Low satisfaction rate (<70%). Review answer quality.")

    if insights:
        for insight in insights:
            report.append(f"  {insight}")
    else:
        report.append("  Not enough data for insights. Continue monitoring.")

    report.append("")
    report.append("=" * 70)

    return "\n".join(report)


def format_query_history_text(history: list, limit: int = 20) -> str:
    """Format query history as human-readable text."""

    report = []
    report.append("=" * 70)
    report.append(f"Query History (Last {limit} queries)")
    report.append("=" * 70)
    report.append("")

    if not history:
        report.append("No queries recorded yet.")
        return "\n".join(report)

    for i, query in enumerate(history[:limit], 1):
        report.append(f"{i}. {query.get('timestamp', 'N/A')}")
        report.append(f"   Route: {query.get('route', 'unknown').upper()}")
        report.append(f"   Success: {'✓' if query.get('success') else '✗'}")
        if query.get('response_time'):
            report.append(f"   Response Time: {query['response_time']:.2f}s")
        if query.get('num_sources'):
            report.append(f"   Sources: {query['num_sources']}")
        if query.get('had_fallback'):
            report.append(f"   Fallback: {query.get('fallback_reason', 'unknown')}")
        if query.get('question'):
            report.append(f"   Question: {query['question']}")
        report.append("")

    return "\n".join(report)


def export_metrics_json(metrics: Dict[str, Any], output_file: str):
    """Export metrics to JSON file."""
    with open(output_file, 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"Metrics exported to: {output_file}")


def export_history_json(history: list, output_file: str):
    """Export query history to JSON file."""
    with open(output_file, 'w') as f:
        json.dump(history, f, indent=2)
    print(f"Query history exported to: {output_file}")


def main():
    """Main entry point for monitoring dashboard."""

    parser = argparse.ArgumentParser(
        description="Generate monitoring reports for RAG + Manual hybrid system"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze (default: 7)"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (for JSON format)"
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Show query history instead of metrics"
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=20,
        help="Number of recent queries to show (default: 20)"
    )
    parser.add_argument(
        "--route",
        choices=["rag", "manual"],
        help="Filter history by route"
    )

    args = parser.parse_args()

    # Initialize monitor
    monitor = QueryMonitor()

    if args.history:
        # Generate query history report
        history = monitor.get_query_history(
            days=args.days,
            route=args.route,
            include_question_text=True
        )

        if args.format == "json":
            output_file = args.output or "query_history.json"
            export_history_json(history, output_file)
        else:
            print(format_query_history_text(history, limit=args.history_limit))

    else:
        # Generate metrics report
        metrics = monitor.get_metrics(days=args.days)

        if args.format == "json":
            output_file = args.output or "metrics.json"
            export_metrics_json(metrics, output_file)
        else:
            print(format_metrics_text(metrics))


if __name__ == "__main__":
    main()
