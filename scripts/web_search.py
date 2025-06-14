#!/usr/bin/env python3
"""Simple script to search the web using Firecrawl.

Set the ``FIRECRAWL_API_KEY`` environment variable with your API key before
running.
"""
import os
import sys
from firecrawl import FirecrawlApp


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: web_search.py <query> (set FIRECRAWL_API_KEY)")
        return 1
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        print("FIRECRAWL_API_KEY environment variable is not set", file=sys.stderr)
        return 1
    query = " ".join(sys.argv[1:])
    app = FirecrawlApp(api_key=api_key)
    result = app.search(query, limit=5)
    for idx, item in enumerate(result.data, start=1):
        title = item.get("title", "")
        url = item.get("url", "")
        desc = item.get("description", "")
        print(f"{idx}. {title}\n{url}\n{desc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
