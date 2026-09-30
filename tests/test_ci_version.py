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
    ("current", "locked", "error"),
    [
        ("0.1.1", "0.1.1", None),
        ("0.1.0", "0.1.0", "Increase"),
        ("0.0.9", "0.0.9", "Increase"),
        ("0.1.1", "0.1.0", "uv.lock"),
        ("0.1.1-dev", "0.1.1-dev", "MAJOR.MINOR.PATCH"),
    ],
)
def test_version_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
        lambda *args, **kwargs: '[project]\nname="djgurda"\nversion="0.1.0"\n',
    )
    if error:
        with pytest.raises(ValueError, match=error):
            version_gate.check("base-sha")
    else:
        version_gate.check("base-sha")
