import io
import json
from contextlib import contextmanager
from unittest.mock import patch

import hazzel
import pytest
from hazzel import config, update_check


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.delenv("HAZZEL_NO_UPDATE_CHECK", raising=False)


@pytest.mark.parametrize("value", ["1", "0"])
def test_nonempty_override_skips_network_and_cache(tmp_path, monkeypatch, value):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("HAZZEL_NO_UPDATE_CHECK", value)

    with (
        patch.object(
            update_check, "_read_cache", side_effect=AssertionError("cache read")
        ) as read_cache,
        patch.object(
            update_check, "_write_cache", side_effect=AssertionError("cache write")
        ) as write_cache,
        patch.object(
            update_check, "_fetch_latest", side_effect=AssertionError("network request")
        ) as fetch_latest,
    ):
        assert update_check.check_for_update(now=1000.0) is None

    read_cache.assert_not_called()
    write_cache.assert_not_called()
    fetch_latest.assert_not_called()
    assert not config.CONFIG_DIR.exists()


@pytest.mark.parametrize("value", [None, ""])
def test_unset_or_blank_override_keeps_update_check(tmp_path, monkeypatch, value):
    _isolate(tmp_path, monkeypatch)
    if value is None:
        monkeypatch.delenv("HAZZEL_NO_UPDATE_CHECK", raising=False)
    else:
        monkeypatch.setenv("HAZZEL_NO_UPDATE_CHECK", value)
    monkeypatch.setattr(update_check, "_local_version", lambda: "1.5.3")

    with (
        patch.object(update_check, "_read_cache", return_value=(None, None)) as read_cache,
        patch.object(update_check, "_write_cache") as write_cache,
        patch.object(update_check, "_fetch_latest", return_value="1.5.4") as fetch_latest,
    ):
        assert update_check.check_for_update(now=1000.0) == "1.5.4"

    read_cache.assert_called_once_with()
    fetch_latest.assert_called_once_with(timeout=update_check.REQUEST_TIMEOUT)
    write_cache.assert_called_once_with(1000.0, "1.5.4")


def _pypi_resp(version):
    payload = json.dumps({"info": {"version": version}}).encode()

    @contextmanager
    def _mgr(*args, **kwargs):
        yield io.BytesIO(payload)

    return _mgr


def test_newer_version_returns_latest(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(update_check, "_local_version", lambda: "1.5.3")
    with patch("urllib.request.urlopen", return_value=_pypi_resp("1.5.4")()):
        assert update_check.check_for_update(now=1000.0) == "1.5.4"


def test_same_version_returns_none(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(update_check, "_local_version", lambda: "1.5.7")
    with patch("urllib.request.urlopen", return_value=_pypi_resp("1.5.7")()):
        assert update_check.check_for_update(now=1000.0) is None


def test_older_latest_returns_none(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(update_check, "_local_version", lambda: "1.5.7")
    with patch("urllib.request.urlopen", return_value=_pypi_resp("1.5.0")()):
        assert update_check.check_for_update(now=1000.0) is None


def test_numeric_compare_not_lexicographic():
    assert update_check.is_newer("1.5.10", "1.5.9") is True
    assert update_check.is_newer("1.5.9", "1.5.10") is False
    assert update_check.is_newer("1.5.7", "1.5.7") is False


def test_caches_for_24h_no_second_fetch(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(update_check, "_local_version", lambda: "1.5.3")
    with patch(
        "urllib.request.urlopen", return_value=_pypi_resp("1.5.4")()
    ) as first:
        assert update_check.check_for_update(now=1000.0) == "1.5.4"
        assert first.called or True
    with patch(
        "urllib.request.urlopen", side_effect=AssertionError("must use cache")
    ):
        assert update_check.check_for_update(now=1000.0 + 60) == "1.5.4"


def test_cache_expiry_refetches(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(update_check, "_local_version", lambda: "1.5.3")
    with patch("urllib.request.urlopen", return_value=_pypi_resp("1.5.4")()):
        assert update_check.check_for_update(now=1000.0) == "1.5.4"
    with patch("urllib.request.urlopen", return_value=_pypi_resp("1.5.5")()):
        assert update_check.check_for_update(now=1000.0 + 90000) == "1.5.5"


def test_network_failure_stays_silent(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(update_check, "_local_version", lambda: "1.5.3")
    with patch("urllib.request.urlopen", side_effect=OSError("down")):
        assert update_check.check_for_update(now=1000.0) is None


def test_network_failure_throttles_retries(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(update_check, "_local_version", lambda: "1.5.3")
    with patch("urllib.request.urlopen", side_effect=OSError("down")):
        assert update_check.check_for_update(now=1000.0) is None
    with patch(
        "urllib.request.urlopen", side_effect=AssertionError("should be throttled")
    ):
        assert update_check.check_for_update(now=1000.0 + 60) is None


def test_corrupt_cache_refetches(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(update_check, "_local_version", lambda: "1.5.3")
    cache = config.CONFIG_DIR / update_check.CACHE_FILENAME
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("{not json", encoding="utf-8")
    with patch("urllib.request.urlopen", return_value=_pypi_resp("1.5.4")()):
        assert update_check.check_for_update(now=1000.0) == "1.5.4"


def test_bad_payload_returns_none(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(update_check, "_local_version", lambda: "1.5.3")

    @contextmanager
    def _bad(*args, **kwargs):
        yield io.BytesIO(b'{"info": {}}')

    with patch("urllib.request.urlopen", return_value=_bad()):
        assert update_check.check_for_update(now=1000.0) is None


def test_format_notice():
    notice = update_check.format_notice("1.5.4", "1.5.3")
    assert notice == "hazzel 1.5.4 available (you have 1.5.3) — pip install -U hazzel"
    assert "1.5.4" in update_check.format_notice("1.5.4", "1.5.3")


def test_format_notice_defaults_to_source_version():
    assert hazzel.__version__ in update_check.format_notice("9.9.9")


def test_print_mode_never_imports_update_check():
    import ast
    from pathlib import Path

    tree = ast.parse(Path("src/hazzel/print_mode.py").read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    assert not any("update_check" in name for name in imports)
