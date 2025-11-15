#!/usr/bin/env python3
"""
BERT-based Complexity Classifier for AI Router
Uses sentence-transformers for semantic similarity-based routing.

Phase 7B: Lightweight ML routing without API dependencies
"""

import logging
from typing import Tuple, List, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Try to import sentence-transformers
try:
    from sentence_transformers import SentenceTransformer, util
    BERT_AVAILABLE = True
except ImportError:
    BERT_AVAILABLE = False
    logger.warning("sentence-transformers not available - BERT routing disabled")


class BERTComplexityClassifier:
    """
    Lightweight BERT-based complexity classifier using sentence similarity.

    Uses all-MiniLM-L6-v2 model (22MB) to compare prompts against reference
    examples of simple vs complex tasks.

    Returns complexity score 0.0 (simple) to 1.0 (complex).
    """

    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        """
        Initialize BERT classifier.

        Args:
            model_name: HuggingFace model name (default: all-MiniLM-L6-v2, 22MB)
        """
        self.model = None
        self.model_name = model_name
        self.available = False

        if not BERT_AVAILABLE:
            logger.warning("BERT classifier unavailable - sentence-transformers not installed")
            return

        try:
            logger.info(f"Loading BERT model: {model_name}...")
            self.model = SentenceTransformer(model_name)
            self.available = True
            logger.info(f"BERT model loaded successfully")

            # Precompute embeddings for reference examples
            self._simple_embeddings = None
            self._complex_embeddings = None
            self._precompute_reference_embeddings()

        except Exception as e:
            logger.error(f"Failed to load BERT model: {e}")
            self.available = False

    @property
    def simple_examples(self) -> List[str]:
        """Reference examples of simple/low-complexity tasks (Ollama-suitable)"""
        return [
            "refactor this function",
            "fix this bug in the code",
            "write a unit test for this class",
            "add error handling to this function",
            "format this code snippet",
            "rename this variable to be more descriptive",
            "add type hints to this function",
            "fix the syntax error in this code",
            "write documentation for this function",
            "create a simple loop to iterate over items",
            "debug this error message",
            "optimize this simple algorithm",
            "add logging to this function",
            "write a helper function for data parsing",
            "implement a basic CRUD operation"
        ]

    @property
    def complex_examples(self) -> List[str]:
        """Reference examples of complex/high-complexity tasks (Claude-suitable)"""
        return [
            "design a microservices architecture for scalability",
            "plan a distributed system with fault tolerance",
            "review security compliance for GDPR requirements",
            "architect a multi-tenant SaaS platform",
            "design a high-performance caching strategy",
            "plan migration from monolith to microservices",
            "analyze performance bottlenecks in distributed system",
            "design event-driven architecture with message queues",
            "plan disaster recovery and backup strategy",
            "architect CI/CD pipeline for multi-region deployment",
            "design database sharding strategy for horizontal scaling",
            "review system design for ASPICE compliance",
            "plan infrastructure for handling millions of users",
            "design real-time data processing pipeline",
            "architect secure authentication system with OAuth2"
        ]

    def _precompute_reference_embeddings(self):
        """Precompute embeddings for reference examples (faster prediction)"""
        if not self.available:
            return

        try:
            logger.info("Precomputing reference embeddings...")
            self._simple_embeddings = self.model.encode(
                self.simple_examples,
                convert_to_tensor=True,
                show_progress_bar=False
            )
            self._complex_embeddings = self.model.encode(
                self.complex_examples,
                convert_to_tensor=True,
                show_progress_bar=False
            )
            logger.info("Reference embeddings computed")
        except Exception as e:
            logger.error(f"Failed to precompute embeddings: {e}")
            self.available = False

    def predict_complexity(self, prompt: str) -> Tuple[float, str]:
        """
        Predict complexity score for a prompt using semantic similarity.

        Args:
            prompt: The user prompt to classify

        Returns:
            Tuple of (complexity_score, explanation)
            - complexity_score: 0.0 (simple) to 1.0 (complex)
            - explanation: Human-readable explanation of the score
        """
        if not self.available:
            return 0.5, "BERT unavailable - fallback to weighted scoring"

        try:
            # Encode prompt
            prompt_embedding = self.model.encode(
                prompt,
                convert_to_tensor=True,
                show_progress_bar=False
            )

            # Compute cosine similarity with simple examples
            simple_similarities = util.cos_sim(
                prompt_embedding,
                self._simple_embeddings
            )[0]
            avg_simple_score = float(simple_similarities.mean())
            max_simple_score = float(simple_similarities.max())

            # Compute cosine similarity with complex examples
            complex_similarities = util.cos_sim(
                prompt_embedding,
                self._complex_embeddings
            )[0]
            avg_complex_score = float(complex_similarities.mean())
            max_complex_score = float(complex_similarities.max())

            # Normalize to 0.0-1.0 scale
            # Higher avg_complex vs avg_simple → higher complexity
            score_diff = avg_complex_score - avg_simple_score
            complexity = (score_diff + 1) / 2  # Map [-1, 1] to [0, 1]

            # Clamp to [0, 1]
            complexity = max(0.0, min(1.0, complexity))

            # Build explanation
            explanation = (
                f"BERT score: {complexity:.2f} "
                f"(simple_sim: {avg_simple_score:.2f}, complex_sim: {avg_complex_score:.2f})"
            )

            logger.debug(
                f"BERT prediction: {complexity:.2f} | "
                f"Simple: avg={avg_simple_score:.2f} max={max_simple_score:.2f} | "
                f"Complex: avg={avg_complex_score:.2f} max={max_complex_score:.2f}"
            )

            return complexity, explanation

        except Exception as e:
            logger.error(f"BERT prediction failed: {e}")
            return 0.5, f"BERT error: {str(e)[:50]}"

    def should_use_claude(
        self,
        prompt: str,
        threshold: float = 0.6
    ) -> Tuple[bool, float, str]:
        """
        Decide if Claude should be used based on BERT complexity score.

        Args:
            prompt: The user prompt
            threshold: Complexity threshold (default: 0.6)

        Returns:
            Tuple of (should_use_claude, complexity_score, reason)
        """
        complexity, explanation = self.predict_complexity(prompt)

        should_use = complexity >= threshold

        reason = (
            f"BERT routing: {complexity:.2f} "
            f"({'≥' if should_use else '<'}{threshold}) - "
            f"{explanation}"
        )

        return should_use, complexity, reason


# Global singleton instance (lazy-loaded)
_bert_classifier_instance: Optional[BERTComplexityClassifier] = None


def get_bert_classifier() -> Optional[BERTComplexityClassifier]:
    """
    Get global BERT classifier instance (singleton pattern).

    Returns None if BERT is unavailable.
    """
    global _bert_classifier_instance

    if not BERT_AVAILABLE:
        return None

    if _bert_classifier_instance is None:
        _bert_classifier_instance = BERTComplexityClassifier()

        # Check if initialization succeeded
        if not _bert_classifier_instance.available:
            _bert_classifier_instance = None
            return None

    return _bert_classifier_instance
