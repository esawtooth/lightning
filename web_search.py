#!/usr/bin/env python3
"""Simple script to search the web using Firecrawl."""
import sys
from firecrawl import FirecrawlApp

API_KEY = "fc-7ba58ac8f0f3489e98c339da3cdb3d73"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: web_search.py <query>")
        return 1
    query = " ".join(sys.argv[1:])
    app = FirecrawlApp(api_key=API_KEY)
    result = app.search(query, limit=5)
    for idx, item in enumerate(result.data, start=1):
        title = item.get("title", "")
        url = item.get("url", "")
        desc = item.get("description", "")
        print(f"{idx}. {title}\n{url}\n{desc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
