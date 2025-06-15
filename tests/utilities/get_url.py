#!/usr/bin/env python3
"""
URL scraping utility using Firecrawl.
Usage: ./get_url.py <url>
"""

import os
import sys
import argparse
from typing import Optional

def scrape_url(url: str, api_key: Optional[str] = None) -> str:
    """Scrape a URL and return markdown content using Firecrawl."""
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
        
        # Scrape the URL
        scrape_result = app.scrape_url(
            url, 
            params={
                'formats': ['markdown', 'html'],
                'includeTags': ['title', 'meta'],
                'excludeTags': ['nav', 'footer', 'aside', 'advertisement']
            }
        )
        
        if scrape_result and 'data' in scrape_result:
            data = scrape_result['data']
            
            # Get the markdown content
            markdown_content = data.get('markdown', '')
            title = data.get('metadata', {}).get('title', 'No title')
            description = data.get('metadata', {}).get('description', '')
            
            # Format the output
            output = f"# {title}\n\n"
            if description:
                output += f"**Description:** {description}\n\n"
            output += f"**URL:** {url}\n\n"
            output += "---\n\n"
            output += markdown_content
            
            return output
        else:
            return f"Failed to scrape URL: {url}"
            
    except Exception as e:
        print(f"Error during URL scraping: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    """Main function for command line usage."""
    parser = argparse.ArgumentParser(description="Scrape a URL and output markdown using Firecrawl")
    parser.add_argument("url", help="URL to scrape")
    parser.add_argument("--api-key", help="Firecrawl API key (overrides environment variable)")
    
    args = parser.parse_args()
    
    if not args.url.strip():
        print("Error: Empty URL", file=sys.stderr)
        sys.exit(1)
    
    # Basic URL validation
    if not (args.url.startswith('http://') or args.url.startswith('https://')):
        print("Error: URL must start with http:// or https://", file=sys.stderr)
        sys.exit(1)
    
    result = scrape_url(args.url, args.api_key)
    print(result)

if __name__ == "__main__":
    main() 