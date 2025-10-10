import pytest
from unittest.mock import Mock, MagicMock, patch, call
from sgcarmart.core.year_navigator import SimpleYearNavigator, discover_historical_pdfs


@pytest.fixture
def mock_playwright():
    with patch('sgcarmart.core.year_navigator.sync_playwright') as mock_pw:
        playwright_instance = MagicMock()
        browser = MagicMock()
        context = MagicMock()
        page = MagicMock()

        mock_pw.return_value.start.return_value = playwright_instance
        playwright_instance.chromium.launch.return_value = browser
        browser.new_context.return_value = context
        context.new_page.return_value = page

        yield {
            'sync_playwright': mock_pw,
            'playwright': playwright_instance,
            'browser': browser,
            'context': context,
            'page': page
        }


class TestSimpleYearNavigator:

    def test_init_default_params(self):
        navigator = SimpleYearNavigator()
        assert navigator.headless is True
        assert navigator.timeout == 15000
        assert navigator.browser is None
        assert navigator.context is None
        assert navigator.page is None

    def test_init_custom_params(self):
        navigator = SimpleYearNavigator(headless=False, timeout=30000)
        assert navigator.headless is False
        assert navigator.timeout == 30000

    def test_start_initializes_browser(self, mock_playwright):
        navigator = SimpleYearNavigator(headless=True)
        navigator.start()

        mock_playwright['sync_playwright'].assert_called_once()
        mock_playwright['playwright'].chromium.launch.assert_called_once_with(headless=True)
        mock_playwright['browser'].new_context.assert_called_once()
        mock_playwright['context'].new_page.assert_called_once()
        mock_playwright['page'].set_default_timeout.assert_called_once_with(15000)

        assert navigator.browser == mock_playwright['browser']
        assert navigator.context == mock_playwright['context']
        assert navigator.page == mock_playwright['page']

    def test_close_cleans_up_resources(self, mock_playwright):
        navigator = SimpleYearNavigator()
        navigator.start()
        navigator.close()

        mock_playwright['page'].close.assert_called_once()
        mock_playwright['context'].close.assert_called_once()
        mock_playwright['browser'].close.assert_called_once()
        mock_playwright['playwright'].stop.assert_called_once()

    def test_context_manager(self, mock_playwright):
        with SimpleYearNavigator() as navigator:
            assert navigator.page is not None

        mock_playwright['page'].close.assert_called_once()
        mock_playwright['context'].close.assert_called_once()
        mock_playwright['browser'].close.assert_called_once()

    def test_parse_date_to_url_format_valid(self):
        navigator = SimpleYearNavigator()
        result = navigator.parse_date_to_url_format('14 October 2024')
        assert result == '2024-10-14'

    def test_parse_date_to_url_format_different_month(self):
        navigator = SimpleYearNavigator()
        result = navigator.parse_date_to_url_format('01 January 2023')
        assert result == '2023-01-01'

    def test_parse_date_to_url_format_invalid(self):
        navigator = SimpleYearNavigator()
        result = navigator.parse_date_to_url_format('invalid date')
        assert result is None

    def test_parse_date_to_url_format_empty(self):
        navigator = SimpleYearNavigator()
        result = navigator.parse_date_to_url_format('')
        assert result is None


class TestGetAvailableYears:

    def test_get_available_years_success(self, mock_playwright):
        navigator = SimpleYearNavigator()
        navigator.start()

        year_selector = MagicMock()
        mock_playwright['page'].locator.return_value.first = year_selector

        div1 = MagicMock()
        div1.inner_text.return_value = '2024'
        div2 = MagicMock()
        div2.inner_text.return_value = '2023'
        div3 = MagicMock()
        div3.inner_text.return_value = 'some text'
        div4 = MagicMock()
        div4.inner_text.return_value = '2022'

        mock_playwright['page'].locator.return_value.all.return_value = [div1, div2, div3, div4]

        years = navigator.get_available_years('82', 'mg')

        assert years == ['2024', '2023', '2022']
        mock_playwright['page'].goto.assert_called_once()
        year_selector.click.assert_called_once()
        mock_playwright['page'].keyboard.press.assert_called_once_with("Escape")

    def test_get_available_years_no_years_found(self, mock_playwright):
        navigator = SimpleYearNavigator()
        navigator.start()

        year_selector = MagicMock()
        mock_playwright['page'].locator.return_value.first = year_selector

        div1 = MagicMock()
        div1.inner_text.return_value = 'no year here'

        mock_playwright['page'].locator.return_value.all.return_value = [div1]

        years = navigator.get_available_years('82', 'mg')

        assert years == []

    def test_get_available_years_handles_duplicates(self, mock_playwright):
        navigator = SimpleYearNavigator()
        navigator.start()

        year_selector = MagicMock()
        mock_playwright['page'].locator.return_value.first = year_selector

        div1 = MagicMock()
        div1.inner_text.return_value = '2024'
        div2 = MagicMock()
        div2.inner_text.return_value = '2024'

        mock_playwright['page'].locator.return_value.all.return_value = [div1, div2]

        years = navigator.get_available_years('82', 'mg')

        assert years == ['2024']

    def test_get_available_years_handles_exception(self, mock_playwright):
        navigator = SimpleYearNavigator()
        navigator.start()

        mock_playwright['page'].goto.side_effect = Exception("Network error")

        years = navigator.get_available_years('82', 'mg')

        assert years == []


class TestGetPdfsForYear:

    def test_get_pdfs_for_year_success(self, mock_playwright):
        navigator = SimpleYearNavigator()
        navigator.start()

        year_selector = MagicMock()
        date_selector = MagicMock()

        def locator_side_effect(selector):
            mock_loc = MagicMock()
            if "Select A Year" in selector:
                mock_loc.first = year_selector
            elif "Select Date of Pricelist" in selector:
                mock_loc.first = date_selector
            else:
                year_div = MagicMock()
                year_div.inner_text.return_value = '2024'

                date_div1 = MagicMock()
                date_div1.inner_text.return_value = '14 October 2024'
                date_div2 = MagicMock()
                date_div2.inner_text.return_value = '01 October 2024'

                mock_loc.all.return_value = [year_div, date_div1, date_div2]
            return mock_loc

        mock_playwright['page'].locator.side_effect = locator_side_effect

        pdfs = navigator.get_pdfs_for_year('82', 'mg', '2024')

        assert len(pdfs) == 2
        assert any(pdf['url'] == 'https://www.sgcarmart.com/new_cars/pricelist/82/2024-10-14.pdf' for pdf in pdfs)
        assert any(pdf['url'] == 'https://www.sgcarmart.com/new_cars/pricelist/82/2024-10-01.pdf' for pdf in pdfs)
        assert all(pdf['year'] == '2024' for pdf in pdfs)

    def test_get_pdfs_for_year_no_year_found(self, mock_playwright):
        navigator = SimpleYearNavigator()
        navigator.start()

        year_selector = MagicMock()
        mock_playwright['page'].locator.return_value.first = year_selector

        div1 = MagicMock()
        div1.inner_text.return_value = '2023'

        mock_playwright['page'].locator.return_value.all.return_value = [div1]

        pdfs = navigator.get_pdfs_for_year('82', 'mg', '2024')

        assert pdfs == []

    def test_get_pdfs_for_year_handles_exception(self, mock_playwright):
        navigator = SimpleYearNavigator()
        navigator.start()

        mock_playwright['page'].goto.side_effect = Exception("Error")

        pdfs = navigator.get_pdfs_for_year('82', 'mg', '2024')

        assert pdfs == []


class TestDiscoverAllPdfs:

    def test_discover_all_pdfs_success(self, mock_playwright):
        navigator = SimpleYearNavigator()
        navigator.start()

        navigator.get_available_years = Mock(return_value=['2024', '2023'])
        navigator.get_pdfs_for_year = Mock(side_effect=[
            [{'url': 'pdf1.pdf', 'date': '2024-10-14', 'filename': 'file1.pdf', 'year': '2024', 'date_text': '14 October 2024'}],
            [{'url': 'pdf2.pdf', 'date': '2023-12-01', 'filename': 'file2.pdf', 'year': '2023', 'date_text': '01 December 2023'}]
        ])

        result = navigator.discover_all_pdfs('82', 'mg')

        assert '2024' in result
        assert '2023' in result
        assert len(result['2024']) == 1
        assert len(result['2023']) == 1
        assert navigator.get_available_years.call_count == 1
        assert navigator.get_pdfs_for_year.call_count == 2

    def test_discover_all_pdfs_no_years(self, mock_playwright):
        navigator = SimpleYearNavigator()
        navigator.start()

        navigator.get_available_years = Mock(return_value=[])

        result = navigator.discover_all_pdfs('82', 'mg')

        assert result == {}

    def test_discover_all_pdfs_year_with_no_pdfs(self, mock_playwright):
        navigator = SimpleYearNavigator()
        navigator.start()

        navigator.get_available_years = Mock(return_value=['2024', '2023'])
        navigator.get_pdfs_for_year = Mock(side_effect=[
            [{'url': 'pdf1.pdf', 'date': '2024-10-14', 'filename': 'file1.pdf', 'year': '2024', 'date_text': '14 October 2024'}],
            []
        ])

        result = navigator.discover_all_pdfs('82', 'mg')

        assert '2024' in result
        assert '2023' not in result
        assert len(result) == 1


class TestDiscoverHistoricalPdfs:

    @patch('sgcarmart.core.year_navigator.SimpleYearNavigator')
    def test_discover_historical_pdfs_success(self, mock_navigator_class):
        mock_navigator = MagicMock()
        mock_navigator.__enter__ = Mock(return_value=mock_navigator)
        mock_navigator.__exit__ = Mock(return_value=None)
        mock_navigator.discover_all_pdfs.return_value = {
            '2024': [{'url': 'pdf1.pdf'}],
            '2023': [{'url': 'pdf2.pdf'}]
        }
        mock_navigator_class.return_value = mock_navigator

        result = discover_historical_pdfs('82', 'mg', headless=True)

        assert '2024' in result
        assert '2023' in result
        mock_navigator_class.assert_called_once_with(headless=True)
        mock_navigator.discover_all_pdfs.assert_called_once_with('82', 'mg', None)

    @patch('sgcarmart.core.year_navigator.SimpleYearNavigator')
    def test_discover_historical_pdfs_headless_false(self, mock_navigator_class):
        mock_navigator = MagicMock()
        mock_navigator.__enter__ = Mock(return_value=mock_navigator)
        mock_navigator.__exit__ = Mock(return_value=None)
        mock_navigator.discover_all_pdfs.return_value = {}
        mock_navigator_class.return_value = mock_navigator

        result = discover_historical_pdfs('82', 'mg', headless=False)

        mock_navigator_class.assert_called_once_with(headless=False)
