"""
Pre-commit repository checks.

Verifies that the repository is safe and complete before committing:
what will be versioned, what must never be, and whether a fresh clone
would actually be reproducible.

Checks performed
----------------
1. No data files or local artefacts staged for versioning
2. No oversized files
3. No credentials or absolute local paths in tracked files
4. All expected project files are present
5. Every Python module compiles
6. Every dbt model has a matching documentation entry

Usage
-----
    python -m scripts.check_repo

Author: Zahia Yanes
"""

import ast
import re
import subprocess
from pathlib import Path

# --- Configuration ---

# Extensions that must never be versioned: data is reproducible from the source.
FORBIDDEN_SUFFIXES = {".csv", ".parquet", ".duckdb", ".zip", ".env", ".pkl"}

# Seeds are the one legitimate exception: they are small, curated reference data.
ALLOWED_DATA_PATHS = {"transform/seeds/"}

MAX_FILE_KB = 500

# Files a reader or a recruiter will look for first.
EXPECTED_FILES = [
    "README.md",
    "LICENSE",
    "Makefile",
    "requirements.txt",
    ".gitignore",
    "docs/CONVENTIONS.md",
    "transform/dbt_project.yml",
    "transform/profiles.yml",
]

# Patterns that would leak an environment or a secret into the repository.
LEAK_PATTERNS = {
    "absolute home path": re.compile(r"/Users/[a-zA-Z.]+/"),
    "possible password": re.compile(r"(?i)(password|passwd)\s*[:=]\s*['\"][^'\"]{3,}"),
    "possible api key": re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"][^'\"]{8,}"),
    "aws access key": re.compile(r"AKIA[0-9A-Z]{16}"),
}

PASS = "  ✅"
FAIL = "  ❌"
WARN = "  ⚠️ "


def tracked_files():
    """
    List files Git would version, including staged and untracked-but-not-ignored.

    Returns
    -------
    list of pathlib.Path
    """
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=True,
    )
    return [Path(line) for line in result.stdout.splitlines() if line]


def check_no_data_files(files):
    """Fail if a data file or local artefact would be versioned."""
    print("\n[1] No data files or local artefacts")
    offenders = [
        path for path in files
        if path.suffix.lower() in FORBIDDEN_SUFFIXES
        and not any(str(path).startswith(allowed) for allowed in ALLOWED_DATA_PATHS)
    ]
    if offenders:
        for path in offenders:
            print(f"{FAIL} {path}")
        return False
    print(f"{PASS} none found ({len(files)} files tracked)")
    return True


def check_file_sizes(files):
    """Fail if a tracked file exceeds the size threshold."""
    print(f"\n[2] No file above {MAX_FILE_KB} KB")
    offenders = [
        (path, path.stat().st_size / 1024)
        for path in files
        if path.exists() and path.stat().st_size > MAX_FILE_KB * 1024
    ]
    if offenders:
        for path, size in offenders:
            print(f"{FAIL} {path} ({size:.0f} KB)")
        return False
    total = sum(path.stat().st_size for path in files if path.exists()) / 1024
    print(f"{PASS} largest files fine, repository total: {total:.0f} KB")
    return True


def check_no_leaks(files):
    """Fail if a tracked text file contains a secret or a machine-specific path."""
    print("\n[3] No credentials or absolute local paths")
    offenders = []
    for path in files:
        if not path.exists() or path.suffix in {".png", ".jpg", ".ico"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError):
            continue
        for label, pattern in LEAK_PATTERNS.items():
            match = pattern.search(content)
            if match:
                offenders.append((path, label, match.group(0)[:60]))

    if offenders:
        for path, label, snippet in offenders:
            print(f"{FAIL} {path}: {label} -> {snippet}")
        return False
    print(f"{PASS} none found")
    return True


def check_expected_files():
    """Report any expected project file that is missing."""
    print("\n[4] Expected project files")
    missing = [name for name in EXPECTED_FILES if not Path(name).exists()]
    for name in EXPECTED_FILES:
        marker = PASS if Path(name).exists() else FAIL
        print(f"{marker} {name}")
    return not missing


def check_python_compiles(files):
    """Fail if any tracked Python module has a syntax error."""
    print("\n[5] Python modules compile")
    offenders = []
    modules = [path for path in files if path.suffix == ".py" and path.exists()]
    for path in modules:
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as error:
            offenders.append((path, error))
    if offenders:
        for path, error in offenders:
            print(f"{FAIL} {path}: line {error.lineno} - {error.msg}")
        return False
    print(f"{PASS} {len(modules)} modules parsed")
    return True


def check_models_documented():
    """Warn about dbt models that have no description in a YAML file."""
    print("\n[6] Every dbt model is documented")
    model_dir = Path("transform/models")
    if not model_dir.exists():
        print(f"{FAIL} {model_dir} not found")
        return False

    models = sorted(path.stem for path in model_dir.rglob("*.sql"))
    documented = "\n".join(
        path.read_text(encoding="utf-8") for path in model_dir.rglob("*.yml")
    )

    undocumented = [name for name in models if f"name: {name}" not in documented]
    if undocumented:
        for name in undocumented:
            print(f"{WARN}{name} has no YAML entry")
        return False
    print(f"{PASS} {len(models)} models documented")
    return True


if __name__ == "__main__":
    print("🔍 Pre-commit repository checks")
    files = tracked_files()

    results = [
        check_no_data_files(files),
        check_file_sizes(files),
        check_no_leaks(files),
        check_expected_files(),
        check_python_compiles(files),
        check_models_documented(),
    ]

    print("\n" + "=" * 60)
    if all(results):
        print("✅ All checks passed - safe to commit")
    else:
        print(f"❌ {results.count(False)} check(s) failed - fix before committing")


def check_lockfile_versioned(files):
    """
    Fail if the dbt package lockfile is not versioned.

    `package-lock.yml` pins exact package versions. Without it, `dbt deps` may
    resolve to a different version on another machine or in CI, silently
    changing the behaviour of macros the models depend on.

    Parameters
    ----------
    files : list of pathlib.Path
        Files Git would version.

    Returns
    -------
    bool
    """
    print("\n[7] dbt package lockfile is versioned")
    lockfile = Path("transform/package-lock.yml")
    if lockfile in files:
        print(f"{PASS} {lockfile} tracked")
        return True
    print(f"{FAIL} {lockfile} missing or ignored - `dbt deps` is not reproducible")
    return False

results = [
        check_no_data_files(files),
        check_file_sizes(files),
        check_no_leaks(files),
        check_expected_files(),
        check_python_compiles(files),
        check_models_documented(),
        check_lockfile_versioned(files),
    ]