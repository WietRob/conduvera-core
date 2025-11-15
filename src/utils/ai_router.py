#!/usr/bin/env python3
"""
Smart AI Router - Budget-based routing between Ollama and Claude
Adapted for Matrix OS from ai-router-system

Version 6.1: Improved with tiktoken and weighted keyword scoring
"""

import os
import json
import requests
import datetime
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import tiktoken for better token estimation
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
    # Use cl100k_base encoding (used by GPT-4, similar to Claude)
    TIKTOKEN_ENCODING = tiktoken.get_encoding("cl100k_base")
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not available - falling back to character-based estimation")


class SmartAIRouter:
    """
    Smart AI Router with budget control.

    Routes AI requests between:
    - Ollama (local, free) for simple tasks
    - Claude API (paid) for complex tasks

    Features:
    - Budget tracking ($5/month default)
    - Keyword-based routing
    - Automatic fallbacks
    - Cost prediction
    """

    def __init__(self, config_path: str = "~/.ai-config/router_config.json"):
        self.config_path = Path(config_path).expanduser()
        self.config = self.load_config()
        self.budget_file = Path(config_path).parent / "budget_tracker.json"

    def load_config(self) -> Dict:
        """Load router configuration."""
        default_config = {
            "ollama_base_url": "http://localhost:11434",
            "monthly_budget": 5.0,
            "warning_threshold": 4.0,
            # High-complexity keywords (weight: +3)
            "high_complexity_keywords": [
                "architecture", "design", "microservices", "scalability",
                "infrastructure", "distributed", "system design"
            ],
            # Medium-complexity keywords (weight: +2)
            "medium_complexity_keywords": [
                "strategy", "planning", "analysis", "review", "compliance",
                "aspice", "security", "performance optimization"
            ],
            # Low-complexity keywords (weight: -2, favors Ollama)
            "low_complexity_keywords": [
                "code", "refactor", "test", "debug", "simple", "function",
                "fix", "error", "syntax", "bug", "typo", "format"
            ],
            # Code indicators (weight: -1, slightly favors Ollama)
            "code_indicators": [
                "variable", "loop", "class", "implement", "write", "create"
            ],
            "cost_per_input_token": 0.000003,  # Claude Sonnet pricing
            "cost_per_output_token": 0.000015,
            "ollama_model": "mistral",
            "prompt_length_threshold": 500  # Long prompts → Claude
        }

        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    default_config.update(config)
                    logger.info(f"Configuration loaded from {self.config_path}")
            else:
                # Create config directory and file
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.config_path, 'w') as f:
                    json.dump(default_config, f, indent=2)
                logger.info(f"Default configuration created: {self.config_path}")
        except Exception as e:
            logger.error(f"Error loading config: {e}")

        self._validate_config(default_config)
        return default_config

    def _validate_config(self, config: Dict):
        """Validate configuration parameters."""
        try:
            if config["monthly_budget"] < 0:
                raise ValueError("monthly_budget must be positive")
            if config["warning_threshold"] < 0:
                raise ValueError("warning_threshold must be positive")
            if config["warning_threshold"] > config["monthly_budget"]:
                logger.warning("warning_threshold is higher than monthly_budget")
        except (KeyError, ValueError) as e:
            logger.error(f"Invalid configuration: {e}")
            raise

    def save_config(self):
        """Save current configuration."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def get_budget_status(self) -> Dict:
        """Get current budget status."""
        current_month = datetime.datetime.now().strftime("%Y-%m")

        if self.budget_file.exists():
            try:
                with open(self.budget_file, 'r') as f:
                    budget_data = json.load(f)
            except Exception as e:
                logger.error(f"Error loading budget data: {e}")
                budget_data = {}
        else:
            budget_data = {}

        if current_month not in budget_data:
            budget_data[current_month] = {
                "spent": 0.0,
                "requests": 0,
                "ollama_requests": 0,
                "claude_requests": 0
            }

        return {
            "current_month": current_month,
            "spent": budget_data[current_month]["spent"],
            "requests": budget_data[current_month]["requests"],
            "ollama_requests": budget_data[current_month].get("ollama_requests", 0),
            "claude_requests": budget_data[current_month].get("claude_requests", 0),
            "budget": self.config["monthly_budget"],
            "remaining": self.config["monthly_budget"] - budget_data[current_month]["spent"],
            "percentage_used": (budget_data[current_month]["spent"] / self.config["monthly_budget"]) * 100,
            "budget_data": budget_data
        }

    def update_budget(self, cost: float, model: str):
        """Update budget tracking."""
        budget_status = self.get_budget_status()
        current_month = budget_status["current_month"]
        budget_data = budget_status["budget_data"]

        budget_data[current_month]["spent"] += cost
        budget_data[current_month]["requests"] += 1

        # Track model-specific requests
        if model.startswith("ollama"):
            budget_data[current_month]["ollama_requests"] = budget_data[current_month].get("ollama_requests", 0) + 1
        else:
            budget_data[current_month]["claude_requests"] = budget_data[current_month].get("claude_requests", 0) + 1

        # Keep only last 3 months
        months_to_keep = sorted(budget_data.keys())[-3:]
        budget_data = {month: budget_data[month] for month in months_to_keep}

        try:
            self.budget_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.budget_file, 'w') as f:
                json.dump(budget_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error updating budget: {e}")

    def should_escalate_to_claude(self, prompt: str) -> Tuple[bool, str]:
        """
        Decide if Claude API is needed using weighted scoring.

        Complexity score calculation:
        - High complexity keywords: +3 each
        - Medium complexity keywords: +2 each
        - Low complexity keywords: -2 each
        - Code indicators: -1 each
        - Long prompt (>500 chars): +1
        - Code blocks present: -1
        - Threshold: score >= 3 → Claude, score < 3 → Ollama
        """
        budget_status = self.get_budget_status()

        # Budget check (hard limit)
        if budget_status["remaining"] <= 0:
            return False, "Budget exhausted - Fallback to Ollama"

        prompt_lower = prompt.lower()
        complexity_score = 0
        reasons = []

        # High complexity keywords (+3 each)
        high_matches = [kw for kw in self.config.get("high_complexity_keywords", []) if kw in prompt_lower]
        if high_matches:
            complexity_score += len(high_matches) * 3
            reasons.append(f"+{len(high_matches)*3} (high: {', '.join(high_matches[:2])})")

        # Medium complexity keywords (+2 each)
        medium_matches = [kw for kw in self.config.get("medium_complexity_keywords", []) if kw in prompt_lower]
        if medium_matches:
            complexity_score += len(medium_matches) * 2
            reasons.append(f"+{len(medium_matches)*2} (medium: {', '.join(medium_matches[:2])})")

        # Low complexity keywords (-2 each)
        low_matches = [kw for kw in self.config.get("low_complexity_keywords", []) if kw in prompt_lower]
        if low_matches:
            complexity_score -= len(low_matches) * 2
            reasons.append(f"-{len(low_matches)*2} (simple: {', '.join(low_matches[:2])})")

        # Code indicators (-1 each)
        code_matches = [kw for kw in self.config.get("code_indicators", []) if kw in prompt_lower]
        if code_matches:
            complexity_score -= len(code_matches)
            reasons.append(f"-{len(code_matches)} (code)")

        # Prompt length check
        if len(prompt) > self.config.get("prompt_length_threshold", 500):
            complexity_score += 1
            reasons.append("+1 (long prompt)")

        # Code block detection (reduces complexity)
        if "```" in prompt:
            complexity_score -= 1
            reasons.append("-1 (code block)")

        # Decision threshold
        threshold = 3
        should_use_claude = complexity_score >= threshold

        # Build reason string
        reason_str = f"Score: {complexity_score} ({'≥' if should_use_claude else '<'}{threshold}) [{', '.join(reasons)}]"

        if should_use_claude:
            return True, f"Complex task - {reason_str}"
        else:
            return False, f"Simple task - {reason_str}"

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Uses tiktoken if available (accurate), otherwise falls back to
        character-based estimation (4 chars ≈ 1 token).

        Returns:
            Estimated token count
        """
        if TIKTOKEN_AVAILABLE:
            try:
                return len(TIKTOKEN_ENCODING.encode(text))
            except Exception as e:
                logger.warning(f"tiktoken encoding failed: {e}, falling back to char estimation")
                return len(text) // 4
        else:
            # Fallback: rough approximation (4 characters ≈ 1 token)
            return len(text) // 4

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Estimate cost for Claude API call.

        NOTE: This is an ESTIMATE only! We use Claude CLI which doesn't
        return actual token counts. For accurate tracking, use Claude API directly.

        Args:
            input_tokens: Estimated input tokens
            output_tokens: Estimated output tokens

        Returns:
            Estimated cost in USD
        """
        input_cost = input_tokens * self.config["cost_per_input_token"]
        output_cost = output_tokens * self.config["cost_per_output_token"]
        return input_cost + output_cost

    def call_ollama(self, prompt: str) -> Dict:
        """Call Ollama API."""
        try:
            url = f"{self.config['ollama_base_url']}/api/generate"
            response = requests.post(
                url,
                json={
                    "model": self.config["ollama_model"],
                    "prompt": prompt,
                    "stream": False
                },
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                return {
                    "success": True,
                    "response": result.get("response", ""),
                    "model": f"ollama/{self.config['ollama_model']}",
                    "cost": 0.0,
                    "tokens": {
                        "input": 0,
                        "output": 0
                    }
                }
            else:
                return {
                    "success": False,
                    "error": f"Ollama API error: {response.status_code}"
                }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "error": "Ollama not running. Start with: ollama serve"
            }
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "Ollama request timeout"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Ollama error: {str(e)}"
            }

    def get_routing_info(self, prompt: str) -> Dict:
        """
        Get routing decision without making the call.

        Returns routing decision with cost estimates.
        NOTE: Costs are ESTIMATED (not measured from actual API response).
        """
        should_use_claude, reason = self.should_escalate_to_claude(prompt)
        budget_status = self.get_budget_status()

        # Estimate tokens using tiktoken (if available) or character-based fallback
        estimated_input_tokens = self.estimate_tokens(prompt)
        # Output tokens: conservative estimate (avg Claude response ~400-600 tokens)
        estimated_output_tokens = 500
        estimated_cost = self.estimate_cost(estimated_input_tokens, estimated_output_tokens)

        return {
            "should_use_claude": should_use_claude,
            "reason": reason,
            "estimated_cost": estimated_cost,
            "estimated_input_tokens": estimated_input_tokens,
            "estimated_output_tokens": estimated_output_tokens,
            "budget_remaining": budget_status["remaining"],
            "budget_percentage_used": budget_status["percentage_used"],
            "recommended_model": "claude" if should_use_claude else "ollama",
            "is_estimate": True,  # Flag that this is not measured!
            "tiktoken_used": TIKTOKEN_AVAILABLE
        }

    def reset_budget(self, month: Optional[str] = None):
        """Reset budget for a specific month (or current month)."""
        if month is None:
            month = datetime.datetime.now().strftime("%Y-%m")

        if self.budget_file.exists():
            try:
                with open(self.budget_file, 'r') as f:
                    budget_data = json.load(f)

                if month in budget_data:
                    budget_data[month] = {
                        "spent": 0.0,
                        "requests": 0,
                        "ollama_requests": 0,
                        "claude_requests": 0
                    }

                    with open(self.budget_file, 'w') as f:
                        json.dump(budget_data, f, indent=2)

                    logger.info(f"Budget reset for {month}")
                    return True
            except Exception as e:
                logger.error(f"Error resetting budget: {e}")

        return False

    def get_monthly_stats(self) -> List[Dict]:
        """Get statistics for all tracked months."""
        if not self.budget_file.exists():
            return []

        try:
            with open(self.budget_file, 'r') as f:
                budget_data = json.load(f)

            stats = []
            for month, data in sorted(budget_data.items(), reverse=True):
                stats.append({
                    "month": month,
                    "spent": data["spent"],
                    "requests": data["requests"],
                    "ollama_requests": data.get("ollama_requests", 0),
                    "claude_requests": data.get("claude_requests", 0),
                    "avg_cost_per_request": data["spent"] / data["requests"] if data["requests"] > 0 else 0.0
                })

            return stats
        except Exception as e:
            logger.error(f"Error getting monthly stats: {e}")
            return []
