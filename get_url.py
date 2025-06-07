#!/usr/bin/env python3
"""Fetch and print markdown from a URL using Firecrawl.

Set the ``FIRECRAWL_API_KEY`` environment variable with your API key before
running.
"""
import os
import sys
from firecrawl import FirecrawlApp


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: get_url.py <url> (set FIRECRAWL_API_KEY)")
        return 1
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        print("FIRECRAWL_API_KEY environment variable is not set", file=sys.stderr)
        return 1
    url = sys.argv[1]
    app = FirecrawlApp(api_key=api_key)
    result = app.scrape_url(url, formats=["markdown"])
    if hasattr(result, "markdown") and result.markdown:
        print(result.markdown)
    else:
        # fallback: if the library returns dict style
        data = getattr(result, "data", {})
        print(data.get("markdown", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
