"""
FreeLLMsTxt Web Application
Dynamic llms.txt generator with beautiful UI
"""

import asyncio
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
import os

app = FastAPI(title="FreeLLMsTxt", description="Dynamic llms.txt Generator")

# CORS middleware for cross-origin requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://arlen-kumar.vercel.app",
        "https://arlenkumar.com",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create templates directory
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)

templates = Jinja2Templates(directory="templates")


# ============== Crawler Classes (Async Version) ==============

@dataclass
class PageInfo:
    """Represents a crawled page"""
    url: str
    title: str = ""
    description: str = ""
    content_preview: str = ""
    links: list[str] = field(default_factory=list)


class AsyncWebCrawler:
    """Async crawler for URL discovery"""
    
    SITEMAP_VARIATIONS = [
        '/sitemap.xml',
        '/sitemap_index.xml',
        '/sitemap-index.xml',
        '/sitemaps.xml',
        '/sitemap1.xml',
        '/sitemap/sitemap.xml',
        '/wp-sitemap.xml',
        '/post-sitemap.xml',
        '/page-sitemap.xml',
    ]
    
    def __init__(self, base_url: str, max_urls: int = 20, timeout: float = 10.0):
        self.base_url = self._normalize_url(base_url)
        self.max_urls = max_urls
        self.timeout = timeout
        self.logs: list[str] = []
        
    def _normalize_url(self, url: str) -> str:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        return url.rstrip('/')
    
    def _log(self, message: str):
        self.logs.append(message)
    
    def _is_same_domain(self, url: str) -> bool:
        base_domain = urlparse(self.base_url).netloc
        url_domain = urlparse(url).netloc
        # Handle www vs non-www
        base_clean = base_domain.replace('www.', '')
        url_clean = url_domain.replace('www.', '')
        return base_clean == url_clean
    
    async def _fetch(self, client: httpx.AsyncClient, url: str) -> Optional[str]:
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as e:
            self._log(f"⚠️ Failed: {url}")
            return None
    
    def _parse_sitemap(self, xml_content: str) -> tuple[list[str], list[str]]:
        urls = []
        nested_sitemaps = []
        
        try:
            xml_content = re.sub(r'xmlns[^"]*"[^"]*"', '', xml_content)
            root = ET.fromstring(xml_content)
            
            for sitemap in root.findall('.//sitemap'):
                loc = sitemap.find('loc')
                if loc is not None and loc.text:
                    nested_sitemaps.append(loc.text.strip())
            
            for url in root.findall('.//url'):
                loc = url.find('loc')
                if loc is not None and loc.text:
                    urls.append(loc.text.strip())
                    
        except ET.ParseError:
            pass
        
        return urls, nested_sitemaps
    
    def _find_sitemaps_in_robots(self, robots_content: str) -> list[str]:
        sitemaps = []
        for line in robots_content.splitlines():
            line = line.strip()
            if line.lower().startswith('sitemap:'):
                sitemap_url = line.split(':', 1)[1].strip()
                if sitemap_url:
                    sitemaps.append(sitemap_url)
        return sitemaps
    
    def _extract_links_from_html(self, html: str, base_url: str) -> list[str]:
        soup = BeautifulSoup(html, 'lxml')
        links = []
        
        for anchor in soup.find_all('a', href=True):
            href = anchor['href']
            if href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue
            
            full_url = urljoin(base_url, href)
            full_url = full_url.split('#')[0]
            
            if self._is_same_domain(full_url) and full_url not in links:
                links.append(full_url)
        
        return links
    
    def _extract_page_info(self, url: str, html: str) -> PageInfo:
        soup = BeautifulSoup(html, 'lxml')
        
        title = ""
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
        
        description = ""
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            description = meta_desc['content']
        
        if not description:
            og_desc = soup.find('meta', attrs={'property': 'og:description'})
            if og_desc and og_desc.get('content'):
                description = og_desc['content']
        
        content_preview = ""
        for tag in soup.find_all(['p', 'article', 'main']):
            text = tag.get_text(strip=True)
            if len(text) > 100:
                content_preview = text[:500] + "..." if len(text) > 500 else text
                break
        
        links = self._extract_links_from_html(html, url)
        
        return PageInfo(
            url=url,
            title=title,
            description=description,
            content_preview=content_preview,
            links=links
        )
    
    async def _crawl_sitemaps(self, client: httpx.AsyncClient, sitemap_urls: list[str], depth: int = 0) -> list[str]:
        if depth > 3:
            return []
        
        all_urls = []
        
        for sitemap_url in sitemap_urls:
            self._log(f"📄 Parsing sitemap: {sitemap_url}")
            content = await self._fetch(client, sitemap_url)
            
            if not content:
                continue
                
            urls, nested_sitemaps = self._parse_sitemap(content)
            all_urls.extend(urls)
            
            if nested_sitemaps:
                self._log(f"📁 Found {len(nested_sitemaps)} nested sitemap(s)")
                all_urls.extend(await self._crawl_sitemaps(client, nested_sitemaps, depth + 1))
        
        return all_urls
    
    async def _crawl_from_homepage(self, client: httpx.AsyncClient) -> list[str]:
        self._log("🔍 No sitemap found. Crawling from homepage...")
        
        urls_to_visit = [self.base_url]
        visited = set()
        discovered = []
        
        while urls_to_visit and len(discovered) < self.max_urls:
            current_url = urls_to_visit.pop(0)
            
            if current_url in visited:
                continue
            
            visited.add(current_url)
            self._log(f"🌐 Crawling: {current_url}")
            
            html = await self._fetch(client, current_url)
            if not html:
                continue
            
            discovered.append(current_url)
            
            links = self._extract_links_from_html(html, current_url)
            for link in links:
                if link not in visited and link not in urls_to_visit:
                    urls_to_visit.append(link)
        
        return discovered
    
    async def discover_and_crawl(self) -> tuple[list[PageInfo], list[str]]:
        """Main discovery and crawl process"""
        self._log(f"🚀 Starting crawl of {self.base_url}")
        
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={'User-Agent': 'FreeLLMsTxt-Bot/1.0'}
        ) as client:
            
            sitemap_urls = []
            
            # Check robots.txt
            robots_url = f"{self.base_url}/robots.txt"
            self._log(f"🤖 Checking robots.txt")
            robots_content = await self._fetch(client, robots_url)
            
            if robots_content:
                sitemap_urls = self._find_sitemaps_in_robots(robots_content)
                if sitemap_urls:
                    self._log(f"✅ Found {len(sitemap_urls)} sitemap(s) in robots.txt")
            
            # Try sitemap variations
            if not sitemap_urls:
                self._log("🔎 Trying common sitemap patterns...")
                for pattern in self.SITEMAP_VARIATIONS:
                    sitemap_url = f"{self.base_url}{pattern}"
                    content = await self._fetch(client, sitemap_url)
                    if content and ('<urlset' in content or '<sitemapindex' in content):
                        self._log(f"✅ Found sitemap: {sitemap_url}")
                        sitemap_urls.append(sitemap_url)
                        break
            
            # Parse sitemaps
            all_urls = []
            if sitemap_urls:
                all_urls = await self._crawl_sitemaps(client, sitemap_urls)
                self._log(f"✅ Found {len(all_urls)} URLs from sitemaps")
            
            # Fallback to HTML crawling
            if not all_urls:
                all_urls = await self._crawl_from_homepage(client)
            
            # Dedupe and limit
            unique_urls = list(dict.fromkeys(all_urls))[:self.max_urls]
            self._log(f"📊 Discovered {len(unique_urls)} unique URLs")
            
            # Crawl pages for content
            self._log("📝 Extracting page information...")
            pages = []
            
            for i, url in enumerate(unique_urls, 1):
                self._log(f"[{i}/{len(unique_urls)}] Fetching: {url}")
                html = await self._fetch(client, url)
                if html:
                    page_info = self._extract_page_info(url, html)
                    pages.append(page_info)
            
            self._log(f"✨ Complete! Crawled {len(pages)} pages")
            return pages, self.logs


# ============== Generator ==============

def generate_llms_txt(base_url: str, pages: list[PageInfo]) -> str:
    """Generate llms.txt content"""
    domain = urlparse(base_url).netloc
    
    # Get site title
    site_title = domain.replace('www.', '').split('.')[0].title()
    site_description = f"Documentation and resources from {domain}"
    
    for page in pages:
        if page.url.rstrip('/') == base_url.rstrip('/') or page.url.rstrip('/') == base_url.replace('://', '://www.').rstrip('/'):
            if page.title:
                site_title = page.title.split(' | ')[0].split(' - ')[0].strip()
            if page.description:
                site_description = page.description
            break
    
    # Categorize pages
    categories: dict[str, list[PageInfo]] = {}
    for page in pages:
        parsed = urlparse(page.url)
        path_parts = [p for p in parsed.path.split('/') if p]
        
        if not path_parts:
            category = "Main"
        else:
            category = path_parts[0].replace('-', ' ').replace('_', ' ').title()
        
        if category not in categories:
            categories[category] = []
        categories[category].append(page)
    
    # Build output
    lines = [f"# {site_title}", "", f"> {site_description}", ""]
    
    sorted_categories = sorted(categories.keys(), key=lambda x: (x != "Main", x))
    
    for category in sorted_categories:
        cat_pages = categories[category]
        
        if category == "Main" and len(cat_pages) == 1:
            page = cat_pages[0]
            title = page.title.split(' | ')[0].split(' - ')[0].strip() if page.title else page.url
            if len(title) > 80:
                title = title[:77] + "..."
            link = f"- [{title}]({page.url})"
            if page.description:
                desc = page.description[:200] + "..." if len(page.description) > 200 else page.description
                link += f": {desc}"
            lines.append(link)
        else:
            lines.append(f"## {category}")
            lines.append("")
            
            for page in sorted(cat_pages, key=lambda p: p.url):
                title = page.title.split(' | ')[0].split(' - ')[0].strip() if page.title else page.url
                if len(title) > 80:
                    title = title[:77] + "..."
                if not title:
                    title = page.url.split('/')[-1] or "Page"
                
                link = f"- [{title}]({page.url})"
                if page.description:
                    desc = page.description[:200] + "..." if len(page.description) > 200 else page.description
                    link += f": {desc}"
                lines.append(link)
            
            lines.append("")
    
    lines.extend([
        "",
        "---",
        f"Generated by FreeLLMsTxt on {datetime.now().strftime('%Y-%m-%d')}",
        f"Source: {base_url}"
    ])
    
    return '\n'.join(lines)


# ============== Routes ==============

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/generate", response_class=JSONResponse)
async def generate(url: str = Form(...), max_urls: int = Form(20)):
    """Generate llms.txt for a URL"""
    try:
        crawler = AsyncWebCrawler(base_url=url, max_urls=max_urls)
        pages, logs = await crawler.discover_and_crawl()
        
        if not pages:
            return JSONResponse({
                "success": False,
                "error": "No pages could be crawled from this URL",
                "logs": logs
            }, status_code=400)
        
        llms_txt = generate_llms_txt(crawler.base_url, pages)
        
        return {
            "success": True,
            "llms_txt": llms_txt,
            "stats": {
                "pages_crawled": len(pages),
                "source_url": crawler.base_url
            },
            "logs": logs
        }
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e),
            "logs": []
        }, status_code=500)


@app.get("/llms.txt", response_class=PlainTextResponse)
async def get_llms_txt(url: str, max_urls: int = 20):
    """Direct endpoint to get llms.txt as plain text"""
    crawler = AsyncWebCrawler(base_url=url, max_urls=max_urls)
    pages, _ = await crawler.discover_and_crawl()
    
    if not pages:
        raise HTTPException(status_code=404, detail="Could not crawl the specified URL")
    
    return generate_llms_txt(crawler.base_url, pages)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

