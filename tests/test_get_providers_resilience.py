"""Regression test for provider discovery tolerating broken model modules.

A single archytas model module that fails to import (e.g. an upstream
dependency mismatch) must not take down provider discovery and, with it, the
entire config/provider-selection UI.
"""
import importlib

import beaker_notebook.lib.config as config_mod


def test_get_providers_tolerates_failing_imports(monkeypatch):
    # Force every per-module import to fail; discovery must degrade to an empty
    # mapping rather than raising.
    config_mod._discover_provider_import_paths.cache_clear()

    def always_fail(name, package=None):
        raise ImportError(f"simulated failure importing {name}")

    monkeypatch.setattr(importlib, "import_module", always_fail)
    try:
        providers = config_mod.get_providers()
    finally:
        config_mod._discover_provider_import_paths.cache_clear()

    assert providers == {}


def test_get_providers_returns_fresh_mapping():
    # The cached discovery is immutable; callers get a fresh dict each call so
    # mutating the result can't corrupt the cache.
    config_mod._discover_provider_import_paths.cache_clear()
    try:
        first = config_mod.get_providers()
        first["__sentinel__"] = "x"
        second = config_mod.get_providers()
        assert "__sentinel__" not in second
    finally:
        config_mod._discover_provider_import_paths.cache_clear()
