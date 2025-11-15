#!/usr/bin/env python3
"""
Feedback Analysis CLI Tool
Analyzes user feedback to suggest routing improvements.

Phase 7C: Active learning from user feedback
"""

import argparse
import json
from pathlib import Path
from collections import Counter
from typing import Dict, List
from feedback_tracker import FeedbackTracker
from ai_router import SmartAIRouter


def generate_report(days: int = 30) -> str:
    """
    Generate comprehensive feedback analysis report.

    Args:
        days: Number of days to analyze

    Returns:
        Formatted report text
    """
    tracker = FeedbackTracker()
    router = SmartAIRouter()

    # Get feedback stats
    stats = tracker.get_feedback_stats(days=days)

    if stats["total_feedback"] == 0:
        return f"📊 No feedback data available for the last {days} days.\n"

    # Build report
    report = []
    report.append("=" * 70)
    report.append(f"Matrix OS AI Router Feedback Report ({days} days)")
    report.append("=" * 70)
    report.append("")

    # Overall satisfaction
    total = stats["total_feedback"]
    thumbs_up = stats["ratings"]["thumbs_up"]
    thumbs_down = stats["ratings"]["thumbs_down"]
    skip = stats["ratings"]["skip"]

    satisfaction_rate = (thumbs_up / total * 100) if total > 0 else 0

    report.append("📊 OVERALL SATISFACTION")
    report.append("-" * 70)
    report.append(f"  Total Feedback: {total}")
    report.append(f"  👍 Helpful:      {thumbs_up} ({thumbs_up / total * 100:.1f}%)")
    report.append(f"  👎 Not Helpful:  {thumbs_down} ({thumbs_down / total * 100:.1f}%)")
    report.append(f"  ⏭️  Skipped:      {skip} ({skip / total * 100:.1f}%)")
    report.append(f"\n  Satisfaction Rate: {satisfaction_rate:.1f}%")

    if satisfaction_rate >= 90:
        report.append("  Status: ✅ EXCELLENT")
    elif satisfaction_rate >= 75:
        report.append("  Status: ✅ GOOD")
    elif satisfaction_rate >= 60:
        report.append("  Status: ⚠️  ACCEPTABLE")
    else:
        report.append("  Status: ❌ NEEDS IMPROVEMENT")

    report.append("")

    # Model-specific performance
    report.append("🎯 ROUTING ACCURACY")
    report.append("-" * 70)

    routing_acc = stats["routing_accuracy"]

    ollama_total = routing_acc["ollama_total"]
    ollama_correct = routing_acc["ollama_correct"]
    ollama_acc = routing_acc["ollama_accuracy"]

    claude_total = routing_acc["claude_total"]
    claude_correct = routing_acc["claude_correct"]
    claude_acc = routing_acc["claude_accuracy"]

    report.append(f"  Ollama: {ollama_correct}/{ollama_total} correct ({ollama_acc:.1f}%)")
    report.append(f"  Claude: {claude_correct}/{claude_total} correct ({claude_acc:.1f}%)")

    overall_acc = ((ollama_correct + claude_correct) / total * 100) if total > 0 else 0
    report.append(f"\n  Overall Accuracy: {overall_acc:.1f}%")

    report.append("")

    # Misrouted prompts
    misrouted = stats["misrouted"]
    total_misrouted = misrouted["total"]

    if total_misrouted > 0:
        report.append("❌ MISROUTED PROMPTS")
        report.append("-" * 70)
        report.append(f"  Total Misrouted: {total_misrouted} ({total_misrouted / total * 100:.1f}%)")
        report.append(f"    Ollama mistakes: {misrouted['ollama']} (should've used Claude)")
        report.append(f"    Claude mistakes: {misrouted['claude']} (should've used Ollama)")
        report.append("")

        # Show misrouted examples
        misrouted_prompts = tracker.get_misrouted_prompts(limit=5)
        if misrouted_prompts:
            report.append("  Recent Misrouted Examples:")
            for i, prompt_data in enumerate(misrouted_prompts[:5], 1):
                model = prompt_data["model"]
                prompt_preview = prompt_data["prompt"][:60] + "..." if len(prompt_data["prompt"]) > 60 else prompt_data["prompt"]
                report.append(f"    {i}. [{model}] \"{prompt_preview}\"")

        report.append("")

    # Recommendations
    analysis = tracker.analyze_misrouted_prompts()
    recommendations = analysis.get("recommendations", [])

    if recommendations:
        report.append("💡 RECOMMENDATIONS")
        report.append("-" * 70)

        for i, rec in enumerate(recommendations, 1):
            report.append(f"  {i}. {rec['type'].upper()}")
            report.append(f"     Reason: {rec['reason']}")
            report.append(f"     Action: {rec['suggestion']}")

            if "current_threshold" in rec and "suggested_threshold" in rec:
                report.append(f"     Current: {rec['current_threshold']} → Suggested: {rec['suggested_threshold']}")

            report.append("")

    # Current configuration
    config = router.config
    report.append("⚙️  CURRENT ROUTING CONFIGURATION")
    report.append("-" * 70)
    report.append(f"  Routing Mode: {config.get('routing_mode', 'weighted')}")
    report.append(f"  Complexity Threshold: {config.get('complexity_threshold', 3)}")

    if config.get("use_bert_routing"):
        report.append(f"  BERT Enabled: Yes")
        report.append(f"  BERT Threshold: {config.get('bert_threshold', 0.6)}")
        report.append(f"  BERT Weight (hybrid): {config.get('bert_weight', 0.7)}")
    else:
        report.append(f"  BERT Enabled: No")

    report.append("")

    # Budget impact
    budget_status = router.get_budget_status()
    report.append("💰 BUDGET IMPACT")
    report.append("-" * 70)
    report.append(f"  Monthly Budget: ${budget_status['budget']:.2f}")
    report.append(f"  Spent: ${budget_status['spent']:.2f} ({budget_status['percentage_used']:.1f}%)")
    report.append(f"  Remaining: ${budget_status['remaining']:.2f}")
    report.append(f"\n  Requests: {budget_status['requests']} total")
    report.append(f"    Ollama: {budget_status['ollama_requests']} (free)")
    report.append(f"    Claude: {budget_status['claude_requests']} (paid)")

    report.append("")
    report.append("=" * 70)

    return "\n".join(report)


def export_training_data(output_file: str, min_feedback: bool = False):
    """
    Export feedback data for BERT fine-tuning.

    Args:
        output_file: Path to output JSONL file
        min_feedback: Only export entries with user feedback
    """
    tracker = FeedbackTracker()
    router = SmartAIRouter()

    # Read feedback
    feedback_data = []
    if tracker.feedback_file.exists():
        with open(tracker.feedback_file, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if not min_feedback or entry.get("user_rating") != "skip":
                        feedback_data.append(entry)
                except json.JSONDecodeError:
                    continue

    # Read routing decisions
    routing_data = {}
    if router.routing_log_file.exists():
        with open(router.routing_log_file, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    prompt_hash = entry.get("prompt_hash")
                    if prompt_hash:
                        routing_data[prompt_hash] = entry
                except json.JSONDecodeError:
                    continue

    # Merge feedback with routing decisions
    training_examples = []
    for feedback in feedback_data:
        prompt_hash = feedback.get("prompt_hash")
        routing_entry = routing_data.get(prompt_hash, {})

        # Label: 1 if should use Claude (thumbs up for Claude, thumbs down for Ollama)
        # Label: 0 if should use Ollama (thumbs up for Ollama, thumbs down for Claude)
        model = feedback.get("model", "")
        rating = feedback.get("user_rating", "")

        if rating == "skip":
            continue  # Skip ambiguous feedback

        if rating == "thumbs_up":
            # Correct routing
            label = 1 if "claude" in model else 0
        elif rating == "thumbs_down":
            # Incorrect routing - flip the label
            label = 0 if "claude" in model else 1
        else:
            continue

        training_examples.append({
            "prompt": feedback.get("prompt", ""),
            "label": label,  # 1 = complex (Claude), 0 = simple (Ollama)
            "rating": rating,
            "model_used": model,
            "correct_routing": rating == "thumbs_up",
            "routing_metadata": routing_entry.get("metadata", {})
        })

    # Write to output file
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        for example in training_examples:
            f.write(json.dumps(example) + '\n')

    print(f"✅ Exported {len(training_examples)} training examples to {output_file}")
    print(f"   Distribution: {sum(1 for e in training_examples if e['label'] == 1)} complex, "
          f"{sum(1 for e in training_examples if e['label'] == 0)} simple")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze user feedback to improve AI routing"
    )

    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate feedback analysis report"
    )

    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to analyze (default: 30)"
    )

    parser.add_argument(
        "--export-training",
        metavar="FILE",
        help="Export training data for BERT fine-tuning to FILE"
    )

    parser.add_argument(
        "--min-feedback",
        action="store_true",
        help="Only export entries with explicit feedback (exclude skipped)"
    )

    args = parser.parse_args()

    if args.report:
        report = generate_report(days=args.days)
        print(report)

    elif args.export_training:
        export_training_data(args.export_training, min_feedback=args.min_feedback)

    else:
        # Default: show report
        report = generate_report(days=args.days)
        print(report)


if __name__ == "__main__":
    main()
