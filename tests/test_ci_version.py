"""Exercise the version gate without contacting GitHub."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "check_version", Path(__file__).parents[1] / "scripts/ci/check_version.py"
)
assert spec and spec.loader
version_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(version_gate)


@pytest.mark.parametrize(
    ("base", "current", "locked", "error"),
    [
        ("0.3.0", "2.0.4.0", "2.0.4.0", None),  # First release with the generation prefix.
        ("2.0.4.0", "2.0.4.1", "2.0.4.1", None),
        ("2.0.4.0", "2.0.4.0", "2.0.4.0", "Increase"),
        ("2.0.4.0", "1.9.9.9", "1.9.9.9", "Increase"),
        ("2.0.4.0", "2.0.5", "2.0.5", "GENERATION"),
        ("2.0.4.0", "2.0.4.1-dev", "2.0.4.1-dev", "GENERATION"),
        ("2.0.4.0", "2.0.4.1", "2.0.4.0", "uv.lock"),
    ],
)
def test_version_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    base: str,
    current: str,
    locked: str,
    error: str | None,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("pyproject.toml").write_text(f'[project]\nname="djgurda"\nversion="{current}"\n')
    Path("uv.lock").write_text(f'[[package]]\nname="djgurda"\nversion="{locked}"\n')
    monkeypatch.setattr(
        version_gate.subprocess,
        "check_output",
        lambda *args, **kwargs: f'[project]\nname="djgurda"\nversion="{base}"\n',
    )
    if error:
        with pytest.raises(ValueError, match=error):
            version_gate.check("base-sha")
    else:
        version_gate.check("base-sha")
