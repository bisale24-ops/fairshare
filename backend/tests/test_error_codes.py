"""Every error code the API can return must have a Russian text in the web client."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
MESSAGES = (ROOT.parent / "frontend" / "src" / "messages.ts").read_text()


def _codes_in_source() -> set[str]:
    codes: set[str] = {"split_invalid"}  # SplitError's default
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text()
        codes |= set(re.findall(r'ApiError\(\s*\d+,\s*"([a-z_]+)"', text))
        codes |= set(re.findall(r'SplitError\([^)]*?,\s*"(split_[a-z_]+)"\)', text))
        codes |= set(re.findall(r'SplitError\([^)]*?,\s*"(split_[a-z_]+)"', text))
    return codes


def test_every_error_code_is_translated_in_the_web_client():
    codes = _codes_in_source()
    assert len(codes) > 35, codes  # the scan found the codes at all
    missing = sorted(c for c in codes if not re.search(rf"^\s*{c}:", MESSAGES, re.M))
    assert not missing, f"add Russian texts for these codes to frontend/src/messages.ts: {missing}"


def test_no_route_raises_a_bare_http_exception():
    """Bare HTTPException(…, 'text') would reach the user in English; use ApiError with a code."""
    for path in (ROOT / "app").rglob("*.py"):
        if path.name == "errors.py":
            continue
        assert not re.search(r"raise HTTPException\(", path.read_text()), path
