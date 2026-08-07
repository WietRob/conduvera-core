"""Packaging and console-script contract tests."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _pyproject_text() -> str:
    return (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")


def _project_scripts() -> dict[str, str]:
    scripts: dict[str, str] = {}
    in_scripts = False
    for raw_line in _pyproject_text().splitlines():
        line = raw_line.strip()
        if line == "[project.scripts]":
            in_scripts = True
            continue
        if in_scripts and line.startswith("["):
            break
        if in_scripts and "=" in line:
            key, value = line.split("=", 1)
            scripts[key.strip()] = value.strip().strip('"')
    return scripts


def _setuptools_package_includes() -> list[str]:
    includes: list[str] = []
    in_find = False
    collecting_include = False
    for raw_line in _pyproject_text().splitlines():
        line = raw_line.strip()
        if line == "[tool.setuptools.packages.find]":
            in_find = True
            continue
        if in_find and line.startswith("["):
            break
        if in_find and line.startswith("include"):
            collecting_include = True
            includes.extend(
                part.strip().strip('"')
                for part in line.split("[", 1)[1].split("]", 1)[0].split(",")
                if part.strip()
            )
            if "]" in line:
                collecting_include = False
            continue
        if collecting_include:
            includes.extend(
                part.strip().strip('"')
                for part in line.split("]", 1)[0].split(",")
                if part.strip()
            )
            if "]" in line:
                collecting_include = False
    return includes


def _project_dependencies() -> set[str]:
    dependencies: set[str] = set()
    in_dependencies = False
    for raw_line in _pyproject_text().splitlines():
        line = raw_line.strip()
        if line.startswith("dependencies") and "[" in line:
            in_dependencies = True
            line = line.split("[", 1)[1]
        elif in_dependencies and "]" in line:
            line = line.split("]", 1)[0]
            in_dependencies = False
        elif not in_dependencies:
            continue

        for item in line.split(","):
            value = item.strip().strip('"')
            if not value:
                continue
            for separator in ("==", ">=", "<=", "~=", "!=", ">", "<"):
                value = value.split(separator, 1)[0]
            dependencies.add(value.lower().replace("_", "-"))
    return dependencies


def _requirement_names() -> set[str]:
    names: set[str] = set()
    for raw_line in (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        name = line.split(";", 1)[0]
        for separator in ("==", ">=", "<=", "~=", "!=", ">", "<"):
            name = name.split(separator, 1)[0]
        names.add(name.strip().lower().replace("_", "-"))
    return names


def test_requirements_include_cli_runtime_dependencies() -> None:
    """requirements.txt supports the documented matrix-cli smoke path."""
    assert "typer" in _requirement_names()


def test_pyproject_includes_cli_runtime_dependencies() -> None:
    """pyproject installs enough runtime dependencies for the matrix-cli entry point."""
    dependencies = _project_dependencies()

    assert "typer" in dependencies


def test_console_scripts_preserve_matrix_os_app_entrypoints() -> None:
    """CuraOps CLI is additive and does not replace the Matrix OS app scripts."""
    scripts = _project_scripts()

    assert scripts["matrix-os"] == "src.core.app:main"
    assert scripts["mxos"] == "src.core.app:main"
    assert scripts["matrix-cli"] == "conduvera.cli.main:main"


def test_setuptools_includes_matrix_os_and_conduvera_packages() -> None:
    """Editable/wheel installs include both the Matrix OS app and CuraOps CLI packages."""
    package_include = _setuptools_package_includes()

    assert "src*" in package_include
    assert "conduvera*" in package_include
