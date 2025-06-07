export type SearchResult = { title: string; url: string; description: string };

const API_BASE = 'https://api.firecrawl.dev/v1';
const API_KEY = process.env['FIRECRAWL_API_KEY'] || '';

async function firecrawlRequest(endpoint: string, body: unknown) {
  if (!API_KEY) {
    throw new Error('FIRECRAWL_API_KEY is not set');
  }
  const res = await fetch(`${API_BASE}/${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${API_KEY}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Firecrawl request failed with status ${res.status}`);
  }
  // The Firecrawl response shape is not currently typed
  // and can vary between endpoints.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (await res.json()) as any;
}

export async function searchWeb(query: string, limit = 5): Promise<Array<SearchResult>> {
  const data = await firecrawlRequest('search', { query, limit });
  return data.data as Array<SearchResult>;
}

export async function getUrlContent(url: string): Promise<string> {
  const data = await firecrawlRequest('scrape', { url, formats: ['markdown'] });
  return data.data?.markdown || '';
}
