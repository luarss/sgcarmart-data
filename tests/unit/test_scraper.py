import pytest
from sgcarmart.core.scraper import (
    scrape_pricelist_links,
    extract_brand_from_url,
)


@pytest.mark.unit
class TestScrapePricelistLinks:
    def test_scrape_valid_html_with_pdfs(self, sample_html_with_pdfs):
        links = scrape_pricelist_links(sample_html_with_pdfs)

        assert len(links) == 3
        assert links[0] == "/new_cars/pricelist/82/2025-01-15.pdf"
        assert links[1] == "/new_cars/pricelist/82/2025-01-10.pdf"
        assert links[2] == "/new_cars/pricelist/82/2024-12-20.pdf"

    def test_scrape_html_without_pdfs(self, sample_html_no_pdfs):
        links = scrape_pricelist_links(sample_html_no_pdfs)

        assert len(links) == 0
        assert links == []

    def test_scrape_empty_html(self):
        links = scrape_pricelist_links("")

        assert len(links) == 0

    def test_scrape_malformed_html(self):
        malformed_html = "<html><div class='wrong-class'><a href='/test.pdf'>Link</a></div>"
        links = scrape_pricelist_links(malformed_html)

        assert len(links) == 0

    def test_scrape_html_with_non_pdf_links(self):
        html = """
        <html>
            <div class="styles_containerDatesContent__nOueF">
                <a class="styles_textPricelistLink__UvFUj" href="/page.html">Page</a>
                <a class="styles_textPricelistLink__UvFUj" href="/image.jpg">Image</a>
            </div>
        </html>
        """
        links = scrape_pricelist_links(html)

        assert len(links) == 0

    def test_scrape_html_with_mixed_links(self):
        html = """
        <html>
            <div class="styles_containerDatesContent__nOueF">
                <a class="styles_textPricelistLink__UvFUj" href="/valid.pdf">Valid</a>
                <a class="styles_textPricelistLink__UvFUj" href="/page.html">Page</a>
                <a class="styles_textPricelistLink__UvFUj" href="/another.pdf">Another</a>
            </div>
        </html>
        """
        links = scrape_pricelist_links(html)

        assert len(links) == 2
        assert links[0] == "/valid.pdf"
        assert links[1] == "/another.pdf"

    def test_scrape_html_with_absolute_urls(self):
        html = """
        <html>
            <div class="styles_containerDatesContent__nOueF">
                <a class="styles_textPricelistLink__UvFUj" href="https://www.sgcarmart.com/file.pdf">File</a>
            </div>
        </html>
        """
        links = scrape_pricelist_links(html)

        assert len(links) == 1
        assert links[0] == "https://www.sgcarmart.com/file.pdf"


@pytest.mark.unit
class TestExtractBrandFromUrl:
    def test_extract_brand_standard_url(self):
        url = "https://www.sgcarmart.com/new-cars/pricelists/82/mg"
        brand = extract_brand_from_url(url)

        assert brand == "mg"

    def test_extract_brand_with_trailing_slash(self):
        url = "https://www.sgcarmart.com/new-cars/pricelists/44/toyota/"
        brand = extract_brand_from_url(url)

        assert brand == "toyota"

    def test_extract_brand_hyphenated(self):
        url = "https://www.sgcarmart.com/new-cars/pricelists/1/alfa-romeo"
        brand = extract_brand_from_url(url)

        assert brand == "alfa-romeo"

    def test_extract_brand_relative_url(self):
        url = "/new-cars/pricelists/4/bmw"
        brand = extract_brand_from_url(url)

        assert brand == "bmw"

    def test_extract_brand_url_without_pricelists(self):
        url = "https://www.sgcarmart.com/about"
        brand = extract_brand_from_url(url)

        assert brand is None

    def test_extract_brand_url_missing_brand(self):
        url = "https://www.sgcarmart.com/new-cars/pricelists/82"
        brand = extract_brand_from_url(url)

        assert brand is None

    def test_extract_brand_empty_url(self):
        brand = extract_brand_from_url("")

        assert brand is None
