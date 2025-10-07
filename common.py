import random
from bs4 import BeautifulSoup

from constants import (
    USER_AGENTS,
    PRICELIST_CONTAINER_CLASS,
    PRICELIST_LINK_CLASS,
)

def normalize_brand_name(brand):
    return brand.lower().replace(" ", "-").replace("_", "-")

def get_random_user_agent():
    return random.choice(USER_AGENTS)

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
