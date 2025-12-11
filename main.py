#!/usr/bin/env python3
"""
FreeLLMsTxt - Automatic llms.txt Generator

Usage:
    python main.py https://example.com
    python main.py https://example.com --max-urls 50 --output custom.txt
"""

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from crawler import WebCrawler
from generator import LLMsTxtGenerator, LLMsTxtConfig

console = Console()


BANNER = """
[bold cyan]╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   [bold white]FreeLLMsTxt[/bold white] - Automatic llms.txt Generator           ║
║                                                           ║
║   Crawls websites and generates llms.txt files           ║
║   for LLM context optimization                            ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝[/bold cyan]
"""


@click.command()
@click.argument('url')
@click.option('--max-urls', '-m', default=20, help='Maximum number of URLs to crawl (default: 20)')
@click.option('--output', '-o', default='llms.txt', help='Output filename (default: llms.txt)')
@click.option('--timeout', '-t', default=10.0, help='Request timeout in seconds (default: 10)')
@click.option('--no-descriptions', is_flag=True, help='Exclude page descriptions from output')
@click.option('--flat', is_flag=True, help='Output as flat list without categories')
def main(url: str, max_urls: int, output: str, timeout: float, no_descriptions: bool, flat: bool):
    """
    Generate an llms.txt file for any website.
    
    URL: The website URL to crawl (e.g., https://example.com)
    
    The tool will:
    
    \b
    1. Check robots.txt for sitemap references
    2. Try common sitemap URL patterns if none found
    3. Parse nested sitemaps recursively
    4. Fall back to HTML link crawling if no sitemap exists
    5. Generate a well-formatted llms.txt file
    """
    console.print(BANNER)
    
    # Initialize crawler
    crawler = WebCrawler(base_url=url, max_urls=max_urls, timeout=timeout)
    
    try:
        # Discover URLs
        urls = crawler.discover_urls()
        
        if not urls:
            console.print("[bold red]✗ No URLs discovered. Please check the URL and try again.[/bold red]")
            return
        
        # Crawl pages for content
        pages = crawler.crawl_pages(urls)
        
        if not pages:
            console.print("[bold red]✗ Could not extract any page information.[/bold red]")
            return
        
        # Generate llms.txt
        config = LLMsTxtConfig(
            include_descriptions=not no_descriptions,
            group_by_path=not flat
        )
        
        generator = LLMsTxtGenerator(
            base_url=crawler.base_url,
            pages=pages,
            config=config
        )
        
        # Save output
        generator.save(output)
        
        # Show summary
        console.print(Panel(
            f"[green]Successfully generated llms.txt![/green]\n\n"
            f"📊 [bold]Stats:[/bold]\n"
            f"   • URLs discovered: {len(urls)}\n"
            f"   • Pages crawled: {len(pages)}\n"
            f"   • Output file: {output}\n\n"
            f"[dim]Open {output} to see the generated content.[/dim]",
            title="[bold]✨ Complete[/bold]",
            border_style="green"
        ))
        
        # Preview the output
        console.print("\n[bold]📄 Preview:[/bold]\n")
        content = generator.generate()
        preview_lines = content.split('\n')[:20]
        for line in preview_lines:
            console.print(f"  [dim]{line}[/dim]")
        if len(content.split('\n')) > 20:
            console.print(f"  [dim]... ({len(content.split(chr(10))) - 20} more lines)[/dim]")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise
    finally:
        crawler.close()


if __name__ == '__main__':
    main()

