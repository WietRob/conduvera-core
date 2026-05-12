# Phase 7 Implementation Plan: BERT Routing + User Feedback

> Deprecated: Historical reference only. This document does not describe the current merged Matrix OS architecture. Use `docs/MATRIX_OS_ARCHITECTURE.md`, `docs/MATRIX_OS_MODULE_BOUNDARIES.md`, `docs/COMPLIANCE_ACCOUNTABILITY_INDEX.md`, and `docs/RELEASE_TRAIN_STATUS.md` as authoritative current docs.


**Status:** 🚧 IN PROGRESS
**Date:** 2025-11-15
**Branch:** `claude/matrix-os-ui-design-comparison-011CV5dNAePdv7fjnr4ABzKW`

## 🎯 Overview

Phase 7 adds ML-based intelligence and user feedback to Matrix OS routing:

- **Phase 7A:** ❌ **CANCELLED** - Claude API (user rejected: "niemals ich will keine schgeiß api")
- **Phase 7B:** ✅ **BERT Classifier** - ML-based complexity detection
- **Phase 7C:** ✅ **User Feedback Loop** - Quality measurement + active learning

**Goal:** Make routing smarter through ML + learn from user feedback!

---

## 📋 Phase 7B: BERT-Based Routing

### Approach: Pragmatic ML

**NOT doing:**
- ❌ Training BERT from scratch (too expensive)
- ❌ Fine-tuning pipeline (too complex for v1)
- ❌ Large model deployment (too slow)

**DOING instead:**
- ✅ Use pretrained BERT via HuggingFace
- ✅ Zero-shot classification or sentence similarity
- ✅ Lightweight distilbert-base model (~66MB)
- ✅ Graceful fallback to weighted scoring
- ✅ Collect training data for future fine-tuning

### Technical Architecture

```python
# Option 1: Zero-shot classification (easiest)
from transformers import pipeline

classifier = pipeline(
    "zero-shot-classification",
    model="facebook/bart-large-mnli"
)

result = classifier(
    prompt,
    candidate_labels=["simple coding task", "complex architecture task"]
)
# → {'labels': [...], 'scores': [0.87, 0.13]}

# Option 2: Sentence similarity (lighter)
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')  # Only 22MB!

# Compare prompt to reference examples
simple_examples = [
    "refactor this function",
    "fix this bug",
    "write a unit test"
]
complex_examples = [
    "design a microservices architecture",
    "plan a distributed system",
    "review security compliance"
]

prompt_embedding = model.encode(prompt)
simple_score = cosine_similarity(prompt_embedding, simple_examples)
complex_score = cosine_similarity(prompt_embedding, complex_examples)
```

### Implementation Strategy

**Stage 1: Add BERT as optional enhancement**
- Install: `transformers`, `sentence-transformers`
- Config flag: `use_bert_routing: true/false`
- Fallback: If BERT fails → weighted scoring (Phase 6.1)

**Stage 2: Hybrid routing**
```python
def should_use_claude(prompt):
    if BERT_AVAILABLE and config["use_bert_routing"]:
        bert_score = bert_classifier.predict_complexity(prompt)
        # 0.0 = simple, 1.0 = complex
        return bert_score > 0.6, f"BERT score: {bert_score:.2f}"
    else:
        # Fallback to weighted scoring
        return weighted_complexity_scoring(prompt)
```

**Stage 3: Ensemble voting** (future)
```python
# Combine BERT + weighted scoring
bert_decision = bert_predict(prompt)  # 0.0-1.0
weighted_decision = weighted_score(prompt) / 10  # Normalize to 0.0-1.0

# Weighted average
final_score = 0.7 * bert_decision + 0.3 * weighted_decision
```

### Data Collection for Fine-Tuning

Every routing decision saves:
```json
{
  "timestamp": "2025-11-15T10:30:00",
  "prompt": "Design a microservices architecture...",
  "prompt_hash": "abc123...",
  "bert_score": 0.85,
  "weighted_score": 6,
  "final_decision": "claude",
  "cost": 0.018,
  "user_feedback": null  // Will be filled by Phase 7C
}
```

Stored in: `~/.ai-config/routing_decisions.jsonl`

---

## 👍 Phase 7C: User Feedback Loop

### UI Design

**After every AI response:**
```
╭─ Neo's Response ──────────────────────╮
│                                        │
│ [AI response text here...]             │
│                                        │
╰────────────────────────────────────────╯

Was this response helpful?
[👍 Yes]  [👎 No]  [⏭️  Skip]
```

**Feedback stored:**
```json
{
  "timestamp": "2025-11-15T10:35:00",
  "prompt": "Design a microservices architecture...",
  "model": "claude",
  "response_length": 1250,
  "routing_score": 0.85,
  "user_rating": "thumbs_up",  // or "thumbs_down", "skip"
  "response_time_seconds": 4.2
}
```

### Feedback Metrics

**Track in Monitoring Dashboard:**
```
🧠 AI BUDGET (2025-11)
⚠️  Estimated costs (not measured)

Spent: ~$0.42 / $5.00 (8.4%)
████████████████░░░░

Requests: 50 total
  🟢 Ollama: 47 (94.0%) - $0.00
  🟡 Claude: 3 (6.0%) - ~$0.42

📊 USER SATISFACTION (NEW!)
  👍 Helpful: 42 (84%)
  👎 Not helpful: 5 (10%)
  ⏭️  Skipped: 3 (6%)

🎯 ROUTING ACCURACY (NEW!)
  ✅ Correct (thumbs up): 42/47 Ollama, 3/3 Claude
  ❌ Incorrect (thumbs down): 5 Ollama (should've used Claude?)
  📈 Accuracy: 90%
```

### Active Learning

**Learn from mistakes:**
```python
def analyze_feedback():
    # Find misrouted prompts
    bad_ollama = [
        f for f in feedback
        if f["model"] == "ollama" and f["rating"] == "thumbs_down"
    ]

    # These should've gone to Claude!
    for prompt_data in bad_ollama:
        print(f"Misrouted: '{prompt_data['prompt'][:50]}...'")
        print(f"  Weighted score: {prompt_data['weighted_score']}")
        print(f"  BERT score: {prompt_data['bert_score']}")
        print(f"  → Should adjust threshold?")

    # Suggest threshold adjustments
    if len(bad_ollama) > 10:
        print("⚠️  Too many Ollama failures! Lower threshold from 3 to 2.5")
```

### Feedback-Driven Improvements

**Weekly reports:**
```
Matrix OS Routing Report (Week 46, 2025)

Total Requests: 247
  Ollama: 198 (80%)
  Claude: 49 (20%)

User Satisfaction:
  👍 Helpful: 215 (87%)
  👎 Not helpful: 20 (8%)
  ⏭️  Skipped: 12 (5%)

Routing Accuracy:
  ✅ Correct Ollama: 190/198 (96%)
  ✅ Correct Claude: 45/49 (92%)
  ❌ Should've been Claude: 8 prompts
  ❌ Should've been Ollama: 4 prompts

Recommendations:
  1. Lower complexity threshold from 3 to 2.8
     (8 prompts got bad Ollama responses)

  2. Add keywords to high_complexity:
     - "scalability" (appeared in 3 misrouted prompts)
     - "distributed" (appeared in 2 misrouted prompts)

  3. BERT model agreement: 95%
     (BERT would've routed correctly 19/20 mistakes)
```

---

## 🛠️ Implementation Plan

### Dependencies

```txt
# Phase 7B: BERT
sentence-transformers>=2.2.0  # Lightweight (22MB model)
# OR
transformers>=4.30.0  # Full BERT support
torch>=2.0.0  # Required for transformers
```

### File Structure

```
src/utils/
  ai_router.py          # Existing, will add BERT support
  bert_classifier.py    # NEW - BERT complexity classifier
  feedback_tracker.py   # NEW - User feedback storage

src/ui/widgets/
  ai_assistant.py       # Modified - Add feedback buttons
  monitoring_dashboard.py  # Modified - Show feedback stats

~/.ai-config/
  router_config.json       # Existing
  budget_tracker.json      # Existing
  routing_decisions.jsonl  # NEW - Training data
  user_feedback.jsonl      # NEW - Feedback tracking
```

### Implementation Steps

**Phase 7B - BERT Classifier:**
1. ✅ Add sentence-transformers to requirements.txt
2. ✅ Create bert_classifier.py with:
   - `BERTComplexityClassifier` class
   - `predict_complexity(prompt) -> float (0.0-1.0)`
   - Reference examples for similarity matching
   - Graceful fallback if model loading fails
3. ✅ Integrate into ai_router.py:
   - Config flag: `use_bert_routing`
   - Hybrid mode: BERT + weighted scoring
   - Log decisions for analysis
4. ✅ Add BERT score to routing info display

**Phase 7C - User Feedback:**
1. ✅ Create feedback_tracker.py with:
   - `FeedbackTracker` class
   - `record_feedback(prompt, model, rating)`
   - `get_feedback_stats()`
   - JSONL storage
2. ✅ Modify ai_assistant.py:
   - Add feedback buttons after response
   - Handle thumbs up/down/skip events
   - Store feedback with routing decision
3. ✅ Modify monitoring_dashboard.py:
   - New "User Satisfaction" section
   - Routing accuracy metrics
   - Misrouted prompt analysis
4. ✅ Add feedback analysis tools:
   - CLI command: `python -m src.utils.analyze_feedback`
   - Generate weekly reports
   - Suggest threshold adjustments

---

## 📊 Success Metrics

### Phase 7B Goals:
- ✅ BERT routing available (even if slower)
- ✅ Accuracy >= weighted scoring (at minimum)
- ✅ Response time < 200ms (with caching)
- ✅ Graceful degradation if BERT fails

### Phase 7C Goals:
- ✅ User feedback on every response
- ✅ 80%+ feedback participation (thumbs up/down/skip)
- ✅ Track routing accuracy over time
- ✅ Identify misrouted prompts within 24h

### Combined Impact:
- 🎯 Routing accuracy: 90% → 95%+
- 📈 User satisfaction: Measurable
- 🔄 Active learning: Continuous improvement
- 🧠 Training data: 100+ labeled examples/week

---

## 🔮 Future Enhancements (Phase 8?)

**With collected data, we can:**

1. **Fine-tune BERT** on actual Matrix OS prompts
   - Train on 1000+ labeled examples
   - Custom model for dev tasks
   - Higher accuracy than zero-shot

2. **A/B Testing**
   - Route 10% of requests both ways
   - Compare response quality
   - Automatic threshold tuning

3. **Multi-label Classification**
   - Not just simple/complex
   - Categories: coding, architecture, debugging, planning, etc.
   - Route to specialized models

4. **Confidence-based routing**
   - BERT score 0.45-0.55? → Ask user!
   - "This is borderline - use Claude ($) or Ollama (free)?"

---

## 🎉 Conclusion

**Phase 7 Plan: ML + Feedback (NO API!)**

✅ **Phase 7B:** BERT makes routing **smarter**
✅ **Phase 7C:** User feedback makes routing **learn**
❌ **Phase 7A:** Keine API-Scheiße! 💪

**Result:** Self-improving routing that gets better every day! 🚀

---

**Ready to implement?** Let's build it! 🔨
