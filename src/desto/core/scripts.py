"""Scripts in the scripts directory: listing, templates and the shell commands that run them.

Shared by the web dashboard, the terminal UI and the CLI, so a script is launched the same
way whichever front end started it.
"""

import re
import shlex
from pathlib import Path

DEFAULT_EXTENSIONS = (".sh", ".py")
SCRIPT_ICONS = {"python": "🐍", "bash": "🐚", "unknown": "📄"}
MAX_NAME_LENGTH = 15

TEMPLATES = {
    "bash": "#!/bin/bash\n\n# Your bash script here\necho 'Hello from desto!'\n",
    "python": "#!/usr/bin/env python3\n\n# Your Python code here\nprint('Hello from desto!')\n",
}
EXTENSIONS = {"bash": ".sh", "python": ".py"}

_NAME_PATTERN = re.compile(rf"^[\w\-]{{1,{MAX_NAME_LENGTH}}}$")


def script_type(filename: str) -> str:
    """Return "python", "bash" or "unknown" from the file extension."""
    if filename.endswith(".py"):
        return "python"
    if filename.endswith(".sh"):
        return "bash"
    return "unknown"


def script_icon(kind: str) -> str:
    """Return the emoji shown next to a script of the given type."""
    return SCRIPT_ICONS.get(kind, SCRIPT_ICONS["unknown"])


def is_valid_name(name: str) -> bool:
    """Session and script names: 1-15 letters, digits, '_' or '-'."""
    return _NAME_PATTERN.match(name or "") is not None


def list_scripts(scripts_dir: Path, extensions=DEFAULT_EXTENSIONS) -> list[str]:
    """Return the sorted file names of the scripts in scripts_dir."""
    names = []
    for ext in extensions:
        names.extend(f.name for f in Path(scripts_dir).glob(f"*{ext}") if f.is_file())
    return sorted(names)


def build_execution_command(script_path, arguments: str = "", python_executable: str = "python3") -> str:
    """Return the shell command that runs one script with its (raw, shell-syntax) arguments."""
    kind = script_type(Path(script_path).name)
    if kind == "python":
        return f"{python_executable} '{script_path}' {arguments}"
    if kind == "bash":
        return f"bash '{script_path}' {arguments}"
    # Fallback: run it directly and rely on its shebang
    return f"'{script_path}' {arguments}"


def launch_command(script_path, arguments: str = "", python_executable: str = "python3") -> str:
    """Command for launching one script: a banner line in the log, then the script."""
    marker = f"echo {shlex.quote(f'=== Running script: {Path(script_path).name} ===')}"
    return f"{marker} && ({build_execution_command(script_path, arguments, python_executable)})"


def chain_command(chain, python_executable: str = "python3") -> str:
    """Command for launching a chain of (script_path, arguments) in order, stopping at the first failure."""
    total = len(chain)
    parts = []
    for idx, (script_path, arguments) in enumerate(chain, 1):
        marker = f"echo {shlex.quote(f'=== Running script {idx} of {total}: {Path(script_path).name} ===')}"
        parts.append(f"{marker} && ({build_execution_command(script_path, arguments, python_executable)})")
    return " && ".join(parts)


def create_script(scripts_dir: Path, name: str, code: str, kind: str = "bash") -> Path:
    """Write a new executable script and return its path.

    Spaces in the name become underscores; a shebang is added when the code has none.

    Raises:
        ValueError: if the name is empty, too long or the type is unknown.
    """
    safe_name = (name or "").strip().replace(" ", "_")
    if not safe_name or len(safe_name) > MAX_NAME_LENGTH:
        raise ValueError(f"Please enter a name up to {MAX_NAME_LENGTH} characters.")
    if kind not in EXTENSIONS:
        raise ValueError(f"Unknown script type: {kind}")
    if not code.startswith("#!"):
        code = TEMPLATES[kind].splitlines(keepends=True)[0] + code
    path = Path(scripts_dir) / f"{safe_name}{EXTENSIONS[kind]}"
    path.write_text(code)
    path.chmod(0o755)
    return path
