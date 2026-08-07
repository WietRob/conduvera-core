# Pattern Learning Engine

Code Pattern Recognition & Learning
Extracted from CuraOps Framework (SW-REQ-079)

## Features

✅ Learn patterns from code findings  
✅ Auto-generate regex patterns  
✅ Scan files for pattern matches  
✅ Pattern confidence scoring  
✅ Pattern persistence (JSON)  
✅ Pattern suggestions  
✅ Statistics & reporting  
✅ **No external dependencies**  

## Installation

```bash
# No external dependencies!
# Only uses Python standard library
```

## Usage

### Python API

```python
from pattern_learning import PatternLearningEngine, CodeFinding

# Initialize
engine = PatternLearningEngine(storage_dir="./.patterns")

# Learn from a finding
finding = CodeFinding(
    description="Hardcoded password",
    code_snippet='password = "secret123"',
    severity="HIGH",
)
pattern = engine.learn_from_finding(finding)
engine.store_pattern(pattern)

# Scan file for patterns
matches = engine.scan_file(Path("src/auth.py"))
for match in matches:
    print(f"Line {match.line_number}: {match.pattern_name}")

# Get suggestions
suggestions = engine.suggest_patterns('api_key = "test"')
for name, confidence in suggestions:
    print(f"{name}: {confidence:.1%}")

# Get stats
stats = engine.get_pattern_stats()
print(f"Total patterns: {stats['total_patterns']}")
print(f"Average confidence: {stats['average_confidence']:.1%}")
```

### CLI

```python
# Learn a new pattern
learn_pattern(
    "./my-project",
    description="Hardcoded password",
    code_snippet='password = "secret"',
    severity="HIGH"
)

# Scan code file
scan_code("./my-project", "src/auth.py")

# List all patterns
list_patterns("./my-project")

# Get suggestions
suggest("./my-project", 'password = "test"')
```

## Pattern Types (Auto-Detected)

### Security Patterns
- `hardcoded_password` - Passwords in code
- `hardcoded_api_key` - API keys in code
- `hardcoded_secret` - Secrets in code
- `hardcoded_token` - Tokens in code

### GDPR/Privacy Patterns
- `exposed_email` - Email addresses
- `exposed_pii` - Personal identifiable info
- `sensitive_logging` - Sensitive data in logs
- `missing_encryption` - Unencrypted sensitive data

### SQL Patterns
- `sql_injection_risk` - SQL injection vulnerabilities
- `injection_vulnerability` - Code injection risks

## Storage Structure

```
.patterns/
└── learned_patterns.json
```

JSON format:
```json
{
  "patterns": [
    {
      "id": "LEARNED-001",
      "name": "hardcoded_password",
      "regex": "password\\s*=\\s*[\"'].*[\"']",
      "severity": "HIGH",
      "description": "Hardcoded password detected",
      "learned_from": "manual",
      "confidence": 0.9,
      "occurrences": 5,
      "created_at": "2026-04-05T13:30:00"
    }
  ],
  "version": "1.0.0",
  "last_updated": "2026-04-05T13:35:00"
}
```

## How It Works

1. **Learning**: Extracts patterns from code findings using heuristics
2. **Storage**: Saves patterns to JSON library
3. **Matching**: Scans code with regex patterns
4. **Scoring**: Confidence based on pattern quality
5. **Suggestions**: Recommends applicable patterns

## Pattern Confidence

- **90%**: Pattern matches original code snippet
- **85%**: Known pattern type (logging, email)
- **60%**: Generic extraction (fallback)
- **0%**: Invalid regex

Confidence increases with each occurrence (+5% per duplicate).

## Tests

```bash
cd ~/.hermes/skills/pattern-learning
python -m pytest tests/ -v
```

9 tests covering:
- Pattern learning
- Pattern storage
- File scanning
- Pattern matching
- Statistics

## Example Output

```
✅ Learned: hardcoded_password (confidence: 90.0%)
✅ Learned: sql_injection_risk (confidence: 60.0%)
✅ Learned: sensitive_logging (confidence: 90.0%)

📊 Pattern Library:
   Total Patterns: 3
   Average Confidence: 80.0%

🔍 Scanning test_code.py:
   Found 2 matches:
   - Line 2: hardcoded_password (HIGH)
   - Line 6: sensitive_logging (HIGH)

💡 Pattern Suggestions:
   - hardcoded_password (90.0%)
```

## Requirements Covered

- SW-REQ-079: Pattern Learning Engine
- SYS-REQ-003: Pattern-Learning System
- US-D3: Pattern Learning Evolution

## Differences from CuraOps Framework

- No `Finding` class dependency (uses `CodeFinding`)
- No prevalence tracker (simplified)
- No feedback integration (simplified)
- Same core learning logic
- Works standalone
