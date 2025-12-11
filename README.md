# FreeLLMsTxt

Automatically generate `llms.txt` files for any website. This tool crawls websites intelligently and creates well-formatted llms.txt files that help LLMs understand your site's structure and content.

![FreeLLMsTxt Screenshot](https://via.placeholder.com/800x400?text=FreeLLMsTxt+Web+Interface)

## What is llms.txt?

`llms.txt` is a proposed standard for providing LLM-friendly documentation about your website. It's similar to `robots.txt` but designed to help AI models understand and navigate your site.

---

## Project Structure

```
FreeLLMsTxt/
├── app.py              # FastAPI web application
├── crawler.py          # URL discovery & page crawling logic
├── generator.py        # llms.txt content generation
├── main.py             # Command-line interface (CLI)
├── requirements.txt    # Python dependencies
├── templates/
│   └── index.html      # Web UI template
└── static/             # Static assets (CSS, JS, images)
```

---

## File Descriptions

### `app.py`
**FastAPI Web Application**

The main web server that provides:
- **`GET /`** - Serves the web interface for generating llms.txt files
- **`POST /generate`** - API endpoint that accepts a URL and returns generated llms.txt content as JSON
- **`GET /llms.txt?url=...`** - Direct API endpoint that returns plain text llms.txt

Contains an async version of the crawler (`AsyncWebCrawler`) optimized for web requests with non-blocking I/O.

```bash
# Run the web server
python app.py
# Or with uvicorn
uvicorn app:app --host 0.0.0.0 --port 8000
```

---

### `crawler.py`
**URL Discovery & Page Crawling**

Core crawling logic with three main classes:

| Class | Purpose |
|-------|---------|
| `SitemapParser` | Parses XML sitemaps and sitemap indexes |
| `RobotsTxtParser` | Extracts sitemap URLs from robots.txt |
| `WebCrawler` | Main crawler that orchestrates URL discovery |

**Discovery Flow:**
1. Check `robots.txt` for `Sitemap:` directives
2. Try common sitemap URL patterns (`/sitemap.xml`, `/wp-sitemap.xml`, etc.)
3. Parse nested sitemaps recursively
4. Fall back to HTML link crawling using BeautifulSoup if no sitemap exists

**Key Features:**
- Handles sitemap indexes (sitemaps of sitemaps)
- Extracts page titles, meta descriptions, and content previews
- Respects same-domain filtering
- Configurable max URL limit (default: 20)

---

### `generator.py`
**llms.txt Content Generation**

Transforms crawled page data into a well-formatted llms.txt file.

| Class | Purpose |
|-------|---------|
| `LLMsTxtConfig` | Configuration options (descriptions, grouping, etc.) |
| `LLMsTxtGenerator` | Generates markdown-formatted llms.txt content |

**Output Features:**
- Site title and description from homepage
- Pages grouped by URL path structure (e.g., `/blog/`, `/docs/`)
- Markdown links with optional descriptions
- Timestamp and source URL footer

---

### `main.py`
**Command-Line Interface**

CLI tool for generating llms.txt files from the terminal.

```bash
# Basic usage
python main.py https://example.com

# With options
python main.py https://example.com --max-urls 50 --output my-site.txt

# Available options
python main.py --help
```

| Option | Description | Default |
|--------|-------------|---------|
| `--max-urls, -m` | Maximum URLs to crawl | 20 |
| `--output, -o` | Output filename | llms.txt |
| `--timeout, -t` | Request timeout (seconds) | 10 |
| `--no-descriptions` | Exclude page descriptions | False |
| `--flat` | Output as flat list | False |

---

### `templates/index.html`
**Web Interface Template**

Single-page web application with:
- Clean Salesforce-inspired design (white + blue theme)
- URL input form
- Real-time crawl progress via logs
- Copy/Download buttons for generated content
- Stats display (pages crawled, source domain)

Built with vanilla HTML, CSS, and JavaScript - no frameworks required.

---

### `requirements.txt`
**Python Dependencies**

```
httpx>=0.25.0          # Async HTTP client
beautifulsoup4>=4.12.0 # HTML parsing
lxml>=4.9.0            # Fast XML/HTML parser
rich>=13.0.0           # Beautiful CLI output
click>=8.1.0           # CLI framework
html2text>=2024.2.26   # HTML to text conversion
fastapi>=0.109.0       # Web framework
uvicorn>=0.27.0        # ASGI server
jinja2>=3.1.0          # Template engine
python-multipart>=0.0.6 # Form data parsing
```

---

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/FreeLLMsTxt.git
cd FreeLLMsTxt

# Install dependencies
pip install -r requirements.txt
```

---

## Usage

### Web Interface

```bash
python app.py
# Open http://localhost:8000
```

### Command Line

```bash
# Generate llms.txt for a website
python main.py https://wrodium.com

# Crawl more pages
python main.py https://docs.python.org --max-urls 50

# Save to custom file
python main.py https://example.com -o custom-output.txt
```

### Direct API

```bash
# Get llms.txt as plain text
curl "http://localhost:8000/llms.txt?url=https://example.com"

# Generate via POST (returns JSON)
curl -X POST "http://localhost:8000/generate" \
  -F "url=https://example.com"
```

---

## How It Works

```
┌─────────────────┐
│  Input URL      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Check robots.txt│ ──→ Found sitemaps? ──→ Parse sitemaps
└────────┬────────┘                              │
         │ No                                    │
         ▼                                       │
┌─────────────────┐                              │
│ Try sitemap     │ ──→ Found? ──────────────────┤
│ URL patterns    │                              │
└────────┬────────┘                              │
         │ No                                    │
         ▼                                       │
┌─────────────────┐                              │
│ Crawl HTML      │ ──→ Extract links ───────────┤
│ from homepage   │     (BeautifulSoup)          │
└─────────────────┘                              │
                                                 │
         ┌───────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Fetch pages     │ ──→ Extract title, description, content
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Generate        │ ──→ Group by URL path
│ llms.txt        │ ──→ Format as markdown
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Output file     │
└─────────────────┘
```

---

## Example Output

```markdown
# Wrodium

> Design content for your marketing strategy and stay ahead of the competition.

- [Wrodium](https://www.wrodium.com/): Design content for your marketing strategy...

## Blog

- [AI Answer Engine Citation Behavior](https://www.wrodium.com/blog/ai-answer-engine...): ...
- [How Wrodium Improves Your AI Search Visibility](https://www.wrodium.com/blog/how-wrodium...): ...

## Docs

- [Getting Started](https://www.wrodium.com/docs/getting-started): ...

---
Generated by FreeLLMsTxt on 2024-12-11
Source: https://wrodium.com
```

---

## License

MIT License - Feel free to use and modify!
