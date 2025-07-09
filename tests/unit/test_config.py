import importlib
import sys

import pytest


@pytest.fixture(autouse=True)
def reset_config_module():
    """Ensure src.app.config is reloaded fresh for each test to respect env overrides."""
    if 'src.app.config' in sys.modules:
        del sys.modules['src.app.config']
    yield
    if 'src.app.config' in sys.modules:
        del sys.modules['src.app.config']


def test_settings_defaults():
    """Default settings should load built-in fallback values."""
    cfg = importlib.import_module('src.app.config')
    settings = cfg.Settings()  # create a fresh instance
    assert settings.api_key == 'mpatel0708'
    assert settings.test_mode is True
    assert settings.request_timeout == 10.0


def test_settings_env_override(monkeypatch):
    """Environment variables should override defaults when present."""
    monkeypatch.setenv('APP_API_KEY', 'override123')
    cfg = importlib.import_module('src.app.config')
    settings = cfg.Settings()  # new instance reflects env
    assert settings.api_key == 'override123'
    # sanity-check that unrelated defaults remain intact
    assert settings.request_timeout == 10.0 