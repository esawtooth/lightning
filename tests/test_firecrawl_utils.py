import sys
import types
import importlib

import pytest


# We test the web_search and get_url command-line scripts


def test_web_search_usage(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['web_search.py'])
    sys.modules.pop('web_search', None)
    module = importlib.import_module('web_search')
    exit_code = module.main()
    captured = capsys.readouterr()
    assert exit_code == 1
    assert 'Usage' in captured.out


def test_web_search_missing_key(monkeypatch, capsys):
    monkeypatch.delenv('FIRECRAWL_API_KEY', raising=False)
    monkeypatch.setattr(sys, 'argv', ['web_search.py', 'hello'])
    sys.modules.pop('web_search', None)
    module = importlib.import_module('web_search')
    exit_code = module.main()
    captured = capsys.readouterr()
    assert exit_code == 1
    assert 'FIRECRAWL_API_KEY environment variable is not set' in captured.err


def test_web_search_success(monkeypatch, capsys):
    captured = {}

    class DummyApp:
        def __init__(self, api_key):
            captured['api_key'] = api_key

        def search(self, query, limit=5):
            captured['query'] = query
            captured['limit'] = limit
            return types.SimpleNamespace(data=[{'title': 't', 'url': 'u', 'description': 'd'}])

    monkeypatch.setenv('FIRECRAWL_API_KEY', 'k')
    monkeypatch.setitem(sys.modules, 'firecrawl', types.SimpleNamespace(FirecrawlApp=DummyApp))
    monkeypatch.setattr(sys, 'argv', ['web_search.py', 'foo', 'bar'])
    sys.modules.pop('web_search', None)
    module = importlib.import_module('web_search')
    exit_code = module.main()
    out = capsys.readouterr().out
    assert exit_code == 0
    assert '1. t' in out
    assert 'u' in out
    assert captured['api_key'] == 'k'
    assert captured['query'] == 'foo bar'
    assert captured['limit'] == 5


def test_get_url_usage(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['get_url.py'])
    sys.modules.pop('get_url', None)
    module = importlib.import_module('get_url')
    exit_code = module.main()
    captured = capsys.readouterr()
    assert exit_code == 1
    assert 'Usage' in captured.out


def test_get_url_missing_key(monkeypatch, capsys):
    monkeypatch.delenv('FIRECRAWL_API_KEY', raising=False)
    monkeypatch.setattr(sys, 'argv', ['get_url.py', 'http://x'])
    sys.modules.pop('get_url', None)
    module = importlib.import_module('get_url')
    exit_code = module.main()
    captured = capsys.readouterr()
    assert exit_code == 1
    assert 'FIRECRAWL_API_KEY environment variable is not set' in captured.err


def test_get_url_success(monkeypatch, capsys):
    captured = {}

    class DummyApp:
        def __init__(self, api_key):
            captured['api_key'] = api_key

        def scrape_url(self, url, formats=None):
            captured['url'] = url
            captured['formats'] = formats
            return types.SimpleNamespace(markdown='# Title', data={'markdown': '# Title'})

    monkeypatch.setenv('FIRECRAWL_API_KEY', 'k')
    monkeypatch.setitem(sys.modules, 'firecrawl', types.SimpleNamespace(FirecrawlApp=DummyApp))
    monkeypatch.setattr(sys, 'argv', ['get_url.py', 'http://example.com'])
    sys.modules.pop('get_url', None)
    module = importlib.import_module('get_url')
    exit_code = module.main()
    out = capsys.readouterr().out
    assert exit_code == 0
    assert '# Title' in out
    assert captured['url'] == 'http://example.com'
    assert captured['formats'] == ['markdown']
    assert captured['api_key'] == 'k'
