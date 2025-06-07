#!/usr/bin/env python3
"""Fetch and print markdown from a URL using Firecrawl."""
import sys
from firecrawl import FirecrawlApp

API_KEY = "fc-7ba58ac8f0f3489e98c339da3cdb3d73"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: get_url.py <url>")
        return 1
    url = sys.argv[1]
    app = FirecrawlApp(api_key=API_KEY)
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
