import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re

class WebsiteScraper:
    def __init__(self, base_url):
        self.base_url = base_url
        self.visited = set()
        self.content = {
            "pages": [],
            "mission": "",
            "services": [],
            "about": "",
            "programs": [],
            "testimonials": [],
            "events": [],
            "contact": {},
            "key_messages": [],
            "brand_voice": "",
            "target_audience": ""
        }

    def scrape(self, max_pages=20):
        """Scrape the website and extract content."""
        self._scrape_page(self.base_url, max_pages)
        self._analyze_content()
        return self.content

    def _scrape_page(self, url, max_pages):
        """Recursively scrape pages."""
        if len(self.visited) >= max_pages:
            return
        if url in self.visited:
            return
        if not url.startswith(self.base_url):
            return

        self.visited.add(url)

        try:
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; ContentBot/1.0)'
            })
            response.raise_for_status()
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return

        soup = BeautifulSoup(response.text, 'lxml')

        # Remove script and style elements
        for element in soup(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()

        # Extract page content
        page_data = {
            "url": url,
            "title": soup.title.string if soup.title else "",
            "headings": [],
            "paragraphs": [],
            "images": [],
            "links": []
        }

        # Get headings
        for tag in ['h1', 'h2', 'h3']:
            for heading in soup.find_all(tag):
                text = heading.get_text(strip=True)
                if text:
                    page_data["headings"].append(text)

        # Get paragraphs
        for p in soup.find_all('p'):
            text = p.get_text(strip=True)
            if len(text) > 50:  # Filter out short snippets
                page_data["paragraphs"].append(text)

        # Get images with alt text
        for img in soup.find_all('img'):
            alt = img.get('alt', '')
            src = img.get('src', '')
            if alt or src:
                page_data["images"].append({"alt": alt, "src": urljoin(url, src)})

        self.content["pages"].append(page_data)

        # Find internal links to scrape
        for link in soup.find_all('a', href=True):
            href = link['href']
            full_url = urljoin(url, href)
            if full_url.startswith(self.base_url) and full_url not in self.visited:
                self._scrape_page(full_url, max_pages)

    def _analyze_content(self):
        """Analyze scraped content to extract key information."""
        all_text = ""
        all_headings = []

        for page in self.content["pages"]:
            all_text += " ".join(page["paragraphs"]) + " "
            all_headings.extend(page["headings"])

        # Look for mission/about content
        mission_keywords = ['mission', 'about', 'who we are', 'our story', 'purpose']
        for page in self.content["pages"]:
            url_lower = page["url"].lower()
            title_lower = page["title"].lower() if page["title"] else ""

            if any(kw in url_lower or kw in title_lower for kw in mission_keywords):
                self.content["about"] = " ".join(page["paragraphs"][:5])

            if 'program' in url_lower or 'service' in url_lower:
                self.content["programs"].extend(page["headings"])

            if 'event' in url_lower:
                self.content["events"].extend(page["headings"])

        # Extract key messages from headings
        self.content["key_messages"] = list(set(all_headings))[:20]

        # Set summary
        self.content["summary"] = all_text[:3000]

        return self.content

    def get_summary(self):
        """Get a formatted summary of the website content."""
        summary = f"""
WEBSITE ANALYSIS: {self.base_url}

PAGES SCRAPED: {len(self.content['pages'])}

KEY MESSAGES/HEADINGS:
{chr(10).join('- ' + h for h in self.content['key_messages'][:15])}

ABOUT/MISSION:
{self.content['about'][:1000] if self.content['about'] else 'Not found - see full content'}

PROGRAMS/SERVICES:
{chr(10).join('- ' + p for p in self.content['programs'][:10]) if self.content['programs'] else 'See full content'}

FULL CONTENT SUMMARY:
{self.content['summary'][:2000]}
"""
        return summary


if __name__ == "__main__":
    scraper = WebsiteScraper("https://projectruth.net/")
    content = scraper.scrape()
    print(scraper.get_summary())
