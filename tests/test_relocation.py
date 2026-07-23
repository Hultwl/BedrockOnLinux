# tests/test_relocation.py
# SPDX-License-Identifier: MIT
"""Tests for the data directory relocation feature."""

import sys
from pathlib import Path

# Add project root to sys.path so 'bol' can be imported
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import os
import pytest
from bol import config


def test_default_install_location():
    """The default location should be ~/.local/share/bedrock-on-linux."""
    expected = str(Path.home() / ".local/share" / "bedrock-on-linux")
    assert config.default_install_location() == expected


def test_is_relocation_allowed(monkeypatch):
    """Relocation should be allowed unless BOL_HOME is set."""
    monkeypatch.delenv("BOL_HOME", raising=False)
    assert config.is_relocation_allowed() is True

    monkeypatch.setenv("BOL_HOME", "/some/path")
    assert config.is_relocation_allowed() is False


def test_set_and_clear_install_location(monkeypatch, tmp_path):
    """set_install_location writes the pointer file; clear removes it."""
    # Override both HOME and INSTALL_LOCATION_FILE to use temp paths
    monkeypatch.setattr(config, "HOME", tmp_path)
    # Reassign INSTALL_LOCATION_FILE to use the new HOME
    monkeypatch.setattr(
        config,
        "INSTALL_LOCATION_FILE",
        tmp_path / ".config" / "bedrock-on-linux" / "install_location"
    )
    monkeypatch.delenv("BOL_HOME", raising=False)

    test_path = tmp_path / "my_custom_data"
    config.set_install_location(str(test_path))

    pointer_file = config.INSTALL_LOCATION_FILE
    assert pointer_file.exists()
    assert pointer_file.read_text().strip() == str(test_path)

    config.clear_install_location()
    assert not pointer_file.exists()


def test_set_install_location_raises_when_bol_home_is_set(monkeypatch):
    """set_install_location should raise RuntimeError when BOL_HOME is set."""
    monkeypatch.setenv("BOL_HOME", "/some/path")
    with pytest.raises(RuntimeError, match="Cannot change location when BOL_HOME is set externally"):
        config.set_install_location("/dummy/path")


def test_clear_install_location_raises_when_bol_home_is_set(monkeypatch):
    """clear_install_location should raise RuntimeError when BOL_HOME is set."""
    monkeypatch.setenv("BOL_HOME", "/some/path")
    with pytest.raises(RuntimeError, match="Cannot change location when BOL_HOME is set externally"):
        config.clear_install_location()


def test_get_install_location():
    """get_install_location returns the same path as config.DATA."""
    assert config.get_install_location() == str(config.DATA)
