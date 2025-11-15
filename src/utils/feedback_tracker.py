#!/usr/bin/env python3
"""
User Feedback Tracker for AI Router
Collects quality ratings to improve routing decisions.

Phase 7C: User feedback loop for active learning
"""

import json
import logging
import datetime
import hashlib
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from collections import Counter

logger = logging.getLogger(__name__)


class FeedbackTracker:
    """
    Track user feedback on AI responses for quality measurement.

    Stores feedback in JSONL format for analysis and active learning.
    """

    def __init__(self, feedback_file: str = "~/.ai-config/user_feedback.jsonl"):
        self.feedback_file = Path(feedback_file).expanduser()
        self.feedback_file.parent.mkdir(parents=True, exist_ok=True)

    def record_feedback(
        self,
        prompt: str,
        model: str,
        rating: str,
        response_length: int = 0,
        routing_score: Optional[float] = None,
        routing_metadata: Optional[Dict] = None,
        response_time: Optional[float] = None
    ):
        """
        Record user feedback for an AI response.

        Args:
            prompt: The user's prompt
            model: Model used (ollama/mistral or claude)
            rating: User rating ("thumbs_up", "thumbs_down", "skip")
            response_length: Length of AI response in characters
            routing_score: Complexity score from router
            routing_metadata: Metadata from routing decision
            response_time: Response time in seconds
        """
        try:
            # Create hash of prompt (for correlation with routing decisions)
            prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]

            feedback_entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "prompt": prompt[:200],  # Truncate for privacy
                "prompt_hash": prompt_hash,
                "model": model,
                "user_rating": rating,
                "response_length": response_length,
                "routing_score": routing_score,
                "routing_metadata": routing_metadata or {},
                "response_time_seconds": response_time
            }

            # Append to JSONL file
            with open(self.feedback_file, 'a') as f:
                f.write(json.dumps(feedback_entry) + '\n')

            logger.info(f"Recorded feedback: {rating} for {model}")

        except Exception as e:
            logger.error(f"Failed to record feedback: {e}")

    def get_feedback_stats(self, days: int = 30) -> Dict:
        """
        Get feedback statistics for the last N days.

        Args:
            days: Number of days to analyze (default: 30)

        Returns:
            Dictionary with feedback statistics
        """
        if not self.feedback_file.exists():
            return self._empty_stats()

        try:
            # Calculate cutoff date
            cutoff = datetime.datetime.now() - datetime.timedelta(days=days)

            # Read and filter feedback
            feedbacks = []
            with open(self.feedback_file, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        entry_time = datetime.datetime.fromisoformat(entry["timestamp"])
                        if entry_time >= cutoff:
                            feedbacks.append(entry)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue

            if not feedbacks:
                return self._empty_stats()

            # Calculate statistics
            total = len(feedbacks)
            ratings = Counter(f["user_rating"] for f in feedbacks)

            # Model-specific stats
            ollama_feedbacks = [f for f in feedbacks if "ollama" in f["model"]]
            claude_feedbacks = [f for f in feedbacks if "claude" in f["model"]]

            # Helper to calculate rating percentages
            def model_stats(model_feedbacks):
                if not model_feedbacks:
                    return {"total": 0, "thumbs_up": 0, "thumbs_down": 0, "skip": 0}

                model_ratings = Counter(f["user_rating"] for f in model_feedbacks)
                return {
                    "total": len(model_feedbacks),
                    "thumbs_up": model_ratings.get("thumbs_up", 0),
                    "thumbs_down": model_ratings.get("thumbs_down", 0),
                    "skip": model_ratings.get("skip", 0)
                }

            # Routing accuracy: thumbs_up = correct decision
            ollama_correct = sum(1 for f in ollama_feedbacks if f["user_rating"] == "thumbs_up")
            claude_correct = sum(1 for f in claude_feedbacks if f["user_rating"] == "thumbs_up")

            # Misrouted: thumbs_down = wrong model choice
            ollama_misrouted = [f for f in ollama_feedbacks if f["user_rating"] == "thumbs_down"]
            claude_misrouted = [f for f in claude_feedbacks if f["user_rating"] == "thumbs_down"]

            return {
                "total_feedback": total,
                "days": days,
                "ratings": {
                    "thumbs_up": ratings.get("thumbs_up", 0),
                    "thumbs_down": ratings.get("thumbs_down", 0),
                    "skip": ratings.get("skip", 0)
                },
                "percentages": {
                    "thumbs_up": (ratings.get("thumbs_up", 0) / total * 100) if total > 0 else 0,
                    "thumbs_down": (ratings.get("thumbs_down", 0) / total * 100) if total > 0 else 0,
                    "skip": (ratings.get("skip", 0) / total * 100) if total > 0 else 0
                },
                "ollama": model_stats(ollama_feedbacks),
                "claude": model_stats(claude_feedbacks),
                "routing_accuracy": {
                    "ollama_correct": ollama_correct,
                    "ollama_total": len(ollama_feedbacks),
                    "ollama_accuracy": (ollama_correct / len(ollama_feedbacks) * 100) if ollama_feedbacks else 0,
                    "claude_correct": claude_correct,
                    "claude_total": len(claude_feedbacks),
                    "claude_accuracy": (claude_correct / len(claude_feedbacks) * 100) if claude_feedbacks else 0
                },
                "misrouted": {
                    "ollama": len(ollama_misrouted),
                    "claude": len(claude_misrouted),
                    "total": len(ollama_misrouted) + len(claude_misrouted)
                }
            }

        except Exception as e:
            logger.error(f"Error getting feedback stats: {e}")
            return self._empty_stats()

    def _empty_stats(self) -> Dict:
        """Return empty statistics structure"""
        return {
            "total_feedback": 0,
            "days": 0,
            "ratings": {"thumbs_up": 0, "thumbs_down": 0, "skip": 0},
            "percentages": {"thumbs_up": 0, "thumbs_down": 0, "skip": 0},
            "ollama": {"total": 0, "thumbs_up": 0, "thumbs_down": 0, "skip": 0},
            "claude": {"total": 0, "thumbs_up": 0, "thumbs_down": 0, "skip": 0},
            "routing_accuracy": {
                "ollama_correct": 0, "ollama_total": 0, "ollama_accuracy": 0,
                "claude_correct": 0, "claude_total": 0, "claude_accuracy": 0
            },
            "misrouted": {"ollama": 0, "claude": 0, "total": 0}
        }

    def get_misrouted_prompts(self, limit: int = 10) -> List[Dict]:
        """
        Get recently misrouted prompts (thumbs_down ratings).

        These prompts should've been sent to a different model.

        Args:
            limit: Maximum number of prompts to return

        Returns:
            List of misrouted prompt entries
        """
        if not self.feedback_file.exists():
            return []

        try:
            misrouted = []
            with open(self.feedback_file, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry["user_rating"] == "thumbs_down":
                            misrouted.append(entry)
                    except (json.JSONDecodeError, KeyError):
                        continue

            # Return most recent first
            misrouted.reverse()
            return misrouted[:limit]

        except Exception as e:
            logger.error(f"Error getting misrouted prompts: {e}")
            return []

    def analyze_misrouted_prompts(self) -> Dict:
        """
        Analyze misrouted prompts to suggest routing improvements.

        Returns:
            Dictionary with analysis and recommendations
        """
        misrouted = self.get_misrouted_prompts(limit=50)

        if not misrouted:
            return {
                "total_misrouted": 0,
                "recommendations": []
            }

        # Group by model
        ollama_mistakes = [m for m in misrouted if "ollama" in m["model"]]
        claude_mistakes = [m for m in misrouted if "claude" in m["model"]]

        recommendations = []

        # Ollama mistakes = should've used Claude (task too complex)
        if ollama_mistakes:
            # Extract keywords from misrouted prompts
            all_prompts = " ".join(m["prompt"].lower() for m in ollama_mistakes)

            recommendations.append({
                "type": "threshold_adjustment",
                "reason": f"{len(ollama_mistakes)} Ollama responses got thumbs down",
                "suggestion": "Consider lowering complexity threshold (route more to Claude)",
                "current_threshold": "3",
                "suggested_threshold": "2.5"
            })

        # Claude mistakes = should've used Ollama (task too simple, wasted money)
        if len(claude_mistakes) > 5:
            recommendations.append({
                "type": "threshold_adjustment",
                "reason": f"{len(claude_mistakes)} Claude responses got thumbs down",
                "suggestion": "Consider raising complexity threshold (route more to Ollama)",
                "current_threshold": "3",
                "suggested_threshold": "3.5"
            })

        return {
            "total_misrouted": len(misrouted),
            "ollama_mistakes": len(ollama_mistakes),
            "claude_mistakes": len(claude_mistakes),
            "recommendations": recommendations
        }
