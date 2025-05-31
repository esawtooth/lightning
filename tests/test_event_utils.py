import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pytest

from events.utils import event_matches


def test_simple_match():
    assert event_matches('llm.chat.request', 'llm.chat.*')


def test_middle_wildcard():
    assert event_matches('llm.chat.request', 'llm.*.request')


def test_no_match():
    assert not event_matches('llm.chat.request', 'llm.chat.response')


def test_exact_match():
    assert event_matches('llm.chat', 'llm.chat')


def test_prefix_wildcard():
    assert event_matches('llm.chat', 'llm.*')
