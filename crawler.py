"""
URL Crawler for llms.txt generation
Handles robots.txt, sitemaps, and HTML link extraction
"""

import re
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Optional
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from rich.console import Console

console = Console()


@dataclass
class PageInfo:
    """Represents a crawled page"""
    url: str
    title: str = ""
    description: str = ""
    content_preview: str = ""
    links: list[str] = field(default_factory=list)


class SitemapParser:
    """Parse XML sitemaps including sitemap indexes"""
    
    SITEMAP_NS = {
        'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9',
        'xhtml': 'http://www.w3.org/1999/xhtml'
    }
    
    @staticmethod
    def parse(xml_content: str) -> tuple[list[str], list[str]]:
        """
        Parse sitemap XML content.
        Returns (urls, nested_sitemaps)
        """
        urls = []
        nested_sitemaps = []
        
        try:
            # Remove namespace prefixes for easier parsing
            xml_content = re.sub(r'xmlns[^"]*"[^"]*"', '', xml_content)
            root = ET.fromstring(xml_content)
            
            # Check if it's a sitemap index
            for sitemap in root.findall('.//sitemap'):
                loc = sitemap.find('loc')
                if loc is not None and loc.text:
                    nested_sitemaps.append(loc.text.strip())
            
            # Get regular URLs
            for url in root.findall('.//url'):
                loc = url.find('loc')
                if loc is not None and loc.text:
                    urls.append(loc.text.strip())
                    
        except ET.ParseError as e:
            console.print(f"[yellow]Warning: Could not parse sitemap XML: {e}[/yellow]")
        
        return urls, nested_sitemaps


class RobotsTxtParser:
    """Parse robots.txt to find sitemap URLs"""
    
    @staticmethod
    def find_sitemaps(robots_content: str) -> list[str]:
        """Extract sitemap URLs from robots.txt"""
        sitemaps = []
        for line in robots_content.splitlines():
            line = line.strip()
            if line.lower().startswith('sitemap:'):
                sitemap_url = line.split(':', 1)[1].strip()
                if sitemap_url:
                    sitemaps.append(sitemap_url)
        return sitemaps


class WebCrawler:
    """Main crawler that discovers URLs from a website"""
    
    SITEMAP_VARIATIONS = [
        '/sitemap.xml',
        '/sitemap_index.xml',
        '/sitemap-index.xml',
        '/sitemaps.xml',
        '/sitemap1.xml',
        '/sitemap/sitemap.xml',
        '/wp-sitemap.xml',  # WordPress
        '/post-sitemap.xml',
        '/page-sitemap.xml',
    ]
    
    def __init__(self, base_url: str, max_urls: int = 20, timeout: float = 10.0):
        self.base_url = self._normalize_url(base_url)
        self.max_urls = max_urls
        self.timeout = timeout
        self.discovered_urls: set[str] = set()
        self.pages: list[PageInfo] = []
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                'User-Agent': 'FreeLLMsTxt-Bot/1.0 (Generating llms.txt)'
            }
        )
        
    def _normalize_url(self, url: str) -> str:
        """Ensure URL has scheme"""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        return url.rstrip('/')
    
    def _is_same_domain(self, url: str) -> bool:
        """Check if URL belongs to the same domain"""
        base_domain = urlparse(self.base_url).netloc
        url_domain = urlparse(url).netloc
        return base_domain == url_domain
    
    def _fetch(self, url: str) -> Optional[str]:
        """Fetch URL content"""
        try:
            response = self.client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as e:
            console.print(f"[dim]Failed to fetch {url}: {e}[/dim]")
            return None
    
    def _get_robots_txt(self) -> Optional[str]:
        """Fetch robots.txt"""
        robots_url = f"{self.base_url}/robots.txt"
        console.print(f"[blue]Checking robots.txt:[/blue] {robots_url}")
        return self._fetch(robots_url)
    
    def _try_sitemap_variations(self) -> list[str]:
        """Try common sitemap URL patterns"""
        console.print("[blue]Trying common sitemap URL patterns...[/blue]")
        found_sitemaps = []
        
        for pattern in self.SITEMAP_VARIATIONS:
            sitemap_url = f"{self.base_url}{pattern}"
            content = self._fetch(sitemap_url)
            if content and ('<urlset' in content or '<sitemapindex' in content):
                console.print(f"[green]✓ Found sitemap:[/green] {sitemap_url}")
                found_sitemaps.append(sitemap_url)
                break  # Use first valid sitemap
        
        return found_sitemaps
    
    def _crawl_sitemaps(self, sitemap_urls: list[str], depth: int = 0) -> list[str]:
        """Recursively crawl sitemaps and return all URLs"""
        if depth > 3:  # Prevent infinite recursion
            return []
        
        all_urls = []
        
        for sitemap_url in sitemap_urls:
            console.print(f"[blue]Parsing sitemap:[/blue] {sitemap_url}")
            content = self._fetch(sitemap_url)
            
            if not content:
                continue
                
            urls, nested_sitemaps = SitemapParser.parse(content)
            all_urls.extend(urls)
            
            if nested_sitemaps:
                console.print(f"[cyan]Found {len(nested_sitemaps)} nested sitemap(s)[/cyan]")
                all_urls.extend(self._crawl_sitemaps(nested_sitemaps, depth + 1))
        
        return all_urls
    
    def _extract_links_from_html(self, html: str, base_url: str) -> list[str]:
        """Extract internal links from HTML content"""
        soup = BeautifulSoup(html, 'lxml')
        links = []
        
        for anchor in soup.find_all('a', href=True):
            href = anchor['href']
            
            # Skip fragment-only links, javascript, mailto, etc.
            if href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue
            
            # Convert relative URLs to absolute
            full_url = urljoin(base_url, href)
            
            # Remove fragments
            full_url = full_url.split('#')[0]
            
            # Only include same-domain links
            if self._is_same_domain(full_url) and full_url not in links:
                links.append(full_url)
        
        return links
    
    def _extract_page_info(self, url: str, html: str) -> PageInfo:
        """Extract title, description, and content from HTML"""
        soup = BeautifulSoup(html, 'lxml')
        
        # Extract title
        title = ""
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
        
        # Extract meta description
        description = ""
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            description = meta_desc['content']
        
        # Extract OG description as fallback
        if not description:
            og_desc = soup.find('meta', attrs={'property': 'og:description'})
            if og_desc and og_desc.get('content'):
                description = og_desc['content']
        
        # Extract content preview (first significant paragraph)
        content_preview = ""
        for tag in soup.find_all(['p', 'article', 'main']):
            text = tag.get_text(strip=True)
            if len(text) > 100:
                content_preview = text[:500] + "..." if len(text) > 500 else text
                break
        
        # Extract links for further crawling
        links = self._extract_links_from_html(html, url)
        
        return PageInfo(
            url=url,
            title=title,
            description=description,
            content_preview=content_preview,
            links=links
        )
    
    def _crawl_from_homepage(self) -> list[str]:
        """Fallback: crawl starting from homepage"""
        console.print("[yellow]No sitemap found. Crawling from homepage...[/yellow]")
        
        urls_to_visit = [self.base_url]
        visited = set()
        discovered = []
        
        while urls_to_visit and len(discovered) < self.max_urls:
            current_url = urls_to_visit.pop(0)
            
            if current_url in visited:
                continue
            
            visited.add(current_url)
            console.print(f"[dim]Crawling:[/dim] {current_url}")
            
            html = self._fetch(current_url)
            if not html:
                continue
            
            discovered.append(current_url)
            
            # Extract links and add to queue
            links = self._extract_links_from_html(html, current_url)
            for link in links:
                if link not in visited and link not in urls_to_visit:
                    urls_to_visit.append(link)
        
        return discovered
    
    def discover_urls(self) -> list[str]:
        """Main discovery process"""
        console.print(f"\n[bold blue]🔍 Discovering URLs for:[/bold blue] {self.base_url}\n")
        
        sitemap_urls = []
        
        # Step 1: Check robots.txt
        robots_content = self._get_robots_txt()
        if robots_content:
            sitemap_urls = RobotsTxtParser.find_sitemaps(robots_content)
            if sitemap_urls:
                console.print(f"[green]✓ Found {len(sitemap_urls)} sitemap(s) in robots.txt[/green]")
        
        # Step 2: Try sitemap variations if none found
        if not sitemap_urls:
            sitemap_urls = self._try_sitemap_variations()
        
        # Step 3: Parse sitemaps
        all_urls = []
        if sitemap_urls:
            all_urls = self._crawl_sitemaps(sitemap_urls)
            console.print(f"[green]✓ Found {len(all_urls)} URLs from sitemaps[/green]")
        
        # Step 4: Fallback to HTML crawling
        if not all_urls:
            all_urls = self._crawl_from_homepage()
        
        # Limit and dedupe URLs
        unique_urls = list(dict.fromkeys(all_urls))[:self.max_urls]
        console.print(f"\n[bold green]✓ Discovered {len(unique_urls)} unique URLs[/bold green]\n")
        
        return unique_urls
    
    def crawl_pages(self, urls: list[str]) -> list[PageInfo]:
        """Crawl pages and extract information"""
        console.print("[bold blue]📄 Extracting page information...[/bold blue]\n")
        
        pages = []
        for i, url in enumerate(urls, 1):
            console.print(f"[dim][{i}/{len(urls)}] Fetching:[/dim] {url}")
            
            html = self._fetch(url)
            if html:
                page_info = self._extract_page_info(url, html)
                pages.append(page_info)
        
        return pages
    
    def close(self):
        """Close HTTP client"""
        self.client.close()

