# Safety Guard Skill

## Installation
```bash
# No external dependencies needed!
# Only uses Python standard library (pathlib)
```

## Usage

### Python
```python
from safety_guard import SafetyGuard, SafetyGuardError

guard = SafetyGuard(project_root="/home/user/projects")

try:
    validated_path = guard.validate_path("/home/user/projects/src/main.py", operation="write")
    print(f"✅ Safe to use: {validated_path}")
except SafetyGuardError as e:
    print(f"🛑 Blocked: {e}")
```

### CLI
```python
# Check path safety
check_path("/home/user/.git/config", operation="write")
# → 🛑 GE BLOCKT: Geschützter Pfad erkannt!

# Validate path
validate_path("/home/user/projects/src/main.py")
# → ✅ Pfad validiert: /home/user/projects/src/main.py
```

## Tests
```bash
cd ~/.hermes/skills/safety-guard
python -m pytest tests/ -v
```

## Protected Paths (Default)
- .git, .gitignore, .gitattributes
- production, prod, live
- secrets, credentials, .env
- vault, system, database
- /etc, /var, /usr, /bin, /sbin

## Requirements Covered
- SW-REQ-048: Path-Validation
- AC1: Empty-Path-Check
- AC2: Absolute-Path-Requirement  
- AC3: Current-Directory-Protection
- AC4: Clear-Error-Messages
- AC5: Project-Boundary-Check
