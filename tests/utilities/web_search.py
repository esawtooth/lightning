#!/usr/bin/env python3
"""
Web search utility using Firecrawl.
Usage: ./web_search.py <query>
"""

import os
import sys
import argparse
from typing import Optional

def search_web(query: str, api_key: Optional[str] = None) -> str:
    """Search the web using Firecrawl and return results."""
    try:
        from firecrawl import FirecrawlApp
    except ImportError:
        print("Error: firecrawl-py package not installed. Run: pip install firecrawl-py", file=sys.stderr)
        sys.exit(1)
    
    # Get API key from environment or parameter
    if not api_key:
        api_key = os.getenv("FIRECRAWL_API_KEY")
    
    if not api_key:
        print("Error: FIRECRAWL_API_KEY environment variable not set", file=sys.stderr)
        print("Set it with: export FIRECRAWL_API_KEY='your-api-key'", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Initialize Firecrawl
        app = FirecrawlApp(api_key=api_key)
        
        # Perform search
        search_result = app.search(query)
        
        if search_result and 'data' in search_result:
            results = []
            for item in search_result['data'][:5]:  # Limit to top 5 results
                title = item.get('title', 'No title')
                url = item.get('url', '')
                description = item.get('description', 'No description')
                
                results.append(f"**{title}**\nURL: {url}\n{description}\n")
            
            return "\n".join(results)
        else:
            return "No search results found."
            
    except Exception as e:
        print(f"Error during web search: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    """Main function for command line usage."""
    parser = argparse.ArgumentParser(description="Search the web using Firecrawl")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--api-key", help="Firecrawl API key (overrides environment variable)")
    
    args = parser.parse_args()
    
    if not args.query.strip():
        print("Error: Empty search query", file=sys.stderr)
        sys.exit(1)
    
    result = search_web(args.query, args.api_key)
    print(result)

if __name__ == "__main__":
    main() 