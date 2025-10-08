from bs4 import BeautifulSoup

from constants import (
    PRICELIST_CONTAINER_CLASS,
    PRICELIST_LINK_CLASS,
    BASE_URL,
    DEFAULT_PAGE_TIMEOUT,
)
from sgcarmart.utils.http import fetch_with_retry, RateLimitException


def scrape_pricelist_links(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    pricelist_links = []

    links_container = soup.find('div', class_=PRICELIST_CONTAINER_CLASS)

    if links_container:
        for link in links_container.find_all('a', class_=PRICELIST_LINK_CLASS):
            pdf_url = link.get('href')
            if pdf_url and isinstance(pdf_url, str) and pdf_url.endswith('.pdf'):
                pricelist_links.append(pdf_url)

    return pricelist_links


def extract_brand_from_url(page_url):
    parts = page_url.rstrip('/').split('/')
    if 'pricelists' in parts:
        pricelists_index = parts.index('pricelists')
        if pricelists_index + 2 < len(parts):
            return parts[pricelists_index + 2]
    return None


def fetch_pricelist_page(page_url):
    try:
        response = fetch_with_retry(page_url, DEFAULT_PAGE_TIMEOUT)
        return response.text, None
    except RateLimitException:
        return None, "Rate limited after retries"
    except Exception as e:
        return None, str(e)
