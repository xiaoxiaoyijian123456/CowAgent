"""Pin the no-browser switch used by the launchd-managed service."""

import pytest

from channel.web.core import channel as channel_module


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "Yes"])
def test_no_open_browser_switch_disables_auto_open(monkeypatch, value):
    monkeypatch.setattr(channel_module, "is_desktop", lambda: False)
    monkeypatch.setenv("COW_NO_OPEN_BROWSER", value)
    assert channel_module._should_auto_open_browser() is False


@pytest.mark.parametrize("value", [None, "", "0", "false", "no"])
def test_empty_or_false_switch_keeps_auto_open(monkeypatch, value):
    monkeypatch.setattr(channel_module, "is_desktop", lambda: False)
    if value is None:
        monkeypatch.delenv("COW_NO_OPEN_BROWSER", raising=False)
    else:
        monkeypatch.setenv("COW_NO_OPEN_BROWSER", value)
    assert channel_module._should_auto_open_browser() is True


def test_desktop_mode_never_auto_opens(monkeypatch):
    monkeypatch.setattr(channel_module, "is_desktop", lambda: True)
    monkeypatch.delenv("COW_NO_OPEN_BROWSER", raising=False)
    assert channel_module._should_auto_open_browser() is False
