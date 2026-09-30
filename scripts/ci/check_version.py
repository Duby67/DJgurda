"""Require a stable version increase against the PR target and a matching lockfile."""

import re
import subprocess
import sys
import tomllib
from pathlib import Path

NUMBER = r"(0|[1-9][0-9]*)"
FORMAT = "GENERATION.MAJOR.MINOR.PATCH"


def release_version(value: str, parts: tuple[int, ...] = (4,)) -> tuple[int, ...]:
    if not any(re.fullmatch(r"\.".join([NUMBER] * count), value) for count in parts):
        raise ValueError(f"Use a version in {FORMAT} format, e.g. 2.0.4.0")
    return tuple(map(int, value.split(".")))


def check(base_ref: str) -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
    base = tomllib.loads(
        subprocess.check_output(["git", "show", f"{base_ref}:pyproject.toml"], text=True)
    )["project"]
    # The base may still carry a MAJOR.MINOR.PATCH version from before the generation prefix.
    if release_version(project["version"]) <= release_version(base["version"], (3, 4)):
        raise ValueError("Increase project.version above development and run uv lock")
    lock = tomllib.loads(Path("uv.lock").read_text())
    packages = [p for p in lock["package"] if p["name"] == project["name"]]
    if len(packages) != 1 or packages[0]["version"] != project["version"]:
        raise ValueError("Project version differs from uv.lock; run uv lock")
    print(f"Version: {base['version']} -> {project['version']}; lockfile matches")


if __name__ == "__main__":
    try:
        check(sys.argv[1])
    except (ValueError, KeyError, IndexError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from None
