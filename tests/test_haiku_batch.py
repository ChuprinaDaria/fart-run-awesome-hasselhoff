"""Tests for HaikuClient batch_explain and config support."""

import time

import pytest

from core.haiku_client import HaikuClient


def test_batch_explain_no_key_returns_empty():
    """Client with no key returns empty dict."""
    client = HaikuClient(api_key=None)
    result = client.batch_explain(["item1", "item2"], context="test", language="en")
    assert result == {}


def test_batch_explain_returns_dict():
    """Empty items list returns empty dict."""
    client = HaikuClient(api_key="sk-ant-test")
    result = client.batch_explain([], context="test", language="en")
    assert result == {}


def test_config_fallback():
    """Client reads api_key from config dict param."""
    config = {"haiku": {"api_key": "sk-ant-from-config"}}
    client = HaikuClient(config=config)
    assert client.is_available()
    assert client._api_key == "sk-ant-from-config"


def test_config_fallback_empty():
    """Empty string key in config means not available."""
    config = {"haiku": {"api_key": ""}}
    client = HaikuClient(config=config)
    assert not client.is_available()


def test_rate_limit_default_30s():
    """_min_interval is 30 seconds."""
    client = HaikuClient(api_key="sk-ant-test")
    assert client._min_interval == 30
