"""
Safety Guard - Path Validation Service
Extracted from CuraOps Framework (SW-REQ-048)

Verhindert Katastrophen wie:
- rm -rf /production
- Überschreiben von .git/
- Zugriff auf /etc/passwd
"""

from pathlib import Path
from typing import List, Optional


class SafetyGuardError(Exception):
    """Exception für Safety Guard Verstöße."""
    pass


class SafetyGuard:
    """
    Safety Guard für Dateisystem-Operationen.
    
    Protects against:
    - Empty/None paths
    - Relative paths  
    - Current directory usage
    - Protected paths (/.git, /production, etc.)
    """
    
    # Default protected paths - can be customized
    DEFAULT_PROTECTED_PATTERNS = [
        ".git",
        ".gitignore", 
        ".gitattributes",
        ".conduvera",
        "production",
        "prod",
        "live",
        "secrets",
        ".secrets",
        "credentials",
        ".env",
        ".env.local",
        ".env.production",
        "vault",
        ".vault",
        "system",
        "config/system",
        "database",
        "db",
        "/etc",
        "/var",
        "/usr",
        "/bin",
        "/sbin",
        "/lib",
        "/opt",
        "/sys",
        "/dev",
        "/proc",
    ]
    
    def __init__(self, project_root: Optional[str] = None, protected_patterns: Optional[List[str]] = None):
        """
        Initialize Safety Guard.
        
        Args:
            project_root: Root directory for the project (for boundary checks)
            protected_patterns: Custom protected path patterns (uses default if None)
        """
        self.project_root = Path(project_root).resolve() if project_root else None
        self.protected_patterns = protected_patterns or self.DEFAULT_PROTECTED_PATTERNS.copy()
    
    def validate_path(self, path: str | Path | None, operation: str = "read") -> Path:
        """
        Validate a path for safety.
        
        Args:
            path: Path to validate (str, Path, or None)
            operation: Type of operation ("read", "write", "delete")
            
        Returns:
            Path: Validated absolute path
            
        Raises:
            SafetyGuardError: If path is unsafe
        """
        # Check 1: Empty/None
        self._check_empty(path)
        
        # Convert to Path
        path_obj = Path(path) if isinstance(path, str) else path
        
        # Check 2: Must be absolute
        self._check_absolute(path_obj)
        
        # Check 3: Resolve and check current directory
        resolved = path_obj.resolve()
        self._check_current_directory(resolved)
        
        # Check 4: Project boundary
        if self.project_root:
            self._check_project_boundary(resolved)
        
        # Check 5: Protected paths
        self._check_protected(resolved, operation)
        
        return resolved
    
    def _check_empty(self, path: str | Path | None) -> None:
        """Check for empty/None paths."""
        if path is None:
            raise SafetyGuardError(
                "KRITISCH: Path ist None! "
                "Verwenden Sie einen absoluten Pfad wie '/home/user/projects/myfile'"
            )
        
        if isinstance(path, str) and (not path or path.strip() == ""):
            raise SafetyGuardError(
                'KRITISCH: Path ist leer! '
                'Path("") würde zu Path.cwd() führen und Daten überschreiben. '
                "Verwenden Sie einen absoluten Pfad."
            )
        
        if isinstance(path, Path):
            if str(path) == "" or str(path) == ".":
                raise SafetyGuardError(
                    'KRITISCH: Path("") oder Path(".") erkannt! '
                    "Dies würde zu Path.cwd() führen. "
                    "Verwenden Sie einen absoluten Pfad."
                )
    
    def _check_absolute(self, path: Path) -> None:
        """Check if path is absolute."""
        if not path.is_absolute():
            raise SafetyGuardError(
                f"KRITISCH: Pfad '{path}' ist relativ! "
                f"Nur absolute Pfade sind erlaubt. "
                f"Verwenden Sie z.B. '/home/user/{path}' statt '{path}'"
            )
    
    def _check_current_directory(self, path: Path) -> None:
        """Check if path points to current directory."""
        current_dir = Path.cwd().resolve()
        
        if path == current_dir:
            raise SafetyGuardError(
                f"KRITISCH: Pfad '{path}' zeigt auf Current-Directory! "
                f"Current-Dir: {current_dir} "
                f"Dies würde aktuelles Verzeichnis überschreiben. "
                f"Verwenden Sie einen EXTERNEN Pfad."
            )
    
    def _check_project_boundary(self, path: Path) -> None:
        """Check if path is within project boundaries."""
        try:
            # Check if path is within project_root
            path.relative_to(self.project_root)
        except ValueError:
            raise SafetyGuardError(
                f"KRITISCH: Pfad '{path}' verlässt Projekt-Grenzen! "
                f"Projekt: {self.project_root} "
                f"Verwenden Sie einen Pfad innerhalb des Projekts."
            )
    
    def _check_protected(self, path: Path, operation: str) -> None:
        """Check against protected path patterns."""
        path_str = str(path)
        
        for pattern in self.protected_patterns:
            # Check if pattern appears in path
            if pattern in path_str:
                # Determine severity based on operation
                if operation == "delete":
                    severity = "🛑 GE BLOCKT"
                    action = "LÖSCHVORGANG VERWEIGERT"
                elif operation == "write":
                    severity = "🛑 GE BLOCKT"
                    action = "SCHREIBVORGANG VERWEIGERT"
                else:  # read
                    severity = "⚠️  WARNUNG"
                    action = "LESEVORGANG ERLAUBT (aber riskant)"
                
                raise SafetyGuardError(
                    f"{severity}: Geschützter Pfad erkannt! "
                    f"Pattern: '{pattern}' in '{path}' "
                    f"{action} "
                    f"Nutzen Sie --force zum Überschreiben (nicht empfohlen)."
                )
    
    def add_protected_pattern(self, pattern: str) -> None:
        """Add a custom protected pattern."""
        if pattern not in self.protected_patterns:
            self.protected_patterns.append(pattern)
    
    def remove_protected_pattern(self, pattern: str) -> None:
        """Remove a protected pattern."""
        if pattern in self.protected_patterns:
            self.protected_patterns.remove(pattern)
    
    def check_safety(self, path: str | Path | None, operation: str = "read") -> tuple[bool, str]:
        """
        Check if path is safe (returns bool instead of raising).
        
        Args:
            path: Path to check
            operation: Operation type
            
        Returns:
            tuple: (is_safe: bool, message: str)
        """
        try:
            self.validate_path(path, operation)
            return True, "✅ Pfad ist sicher"
        except SafetyGuardError as e:
            return False, str(e)


# CLI Interface
def check_path(path: str, project_root: str = None, operation: str = "read") -> str:
    """CLI: Check if path is safe."""
    guard = SafetyGuard(project_root=project_root)
    is_safe, message = guard.check_safety(path, operation)
    return message


def validate_path(path: str, project_root: str = None, operation: str = "read") -> str:
    """CLI: Validate path (raises if unsafe)."""
    try:
        guard = SafetyGuard(project_root=project_root)
        validated = guard.validate_path(path, operation)
        return f"✅ Pfad validiert: {validated}"
    except SafetyGuardError as e:
        return f"🛑 {e}"
