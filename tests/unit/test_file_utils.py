import pytest
import json
import os
from pathlib import Path
from sgcarmart.utils.file_utils import (
    normalize_brand_name,
    ensure_directory,
    load_dealer_brand_mapping,
    extract_metadata_from_url,
)


@pytest.mark.unit
class TestNormalizeBrandName:
    def test_lowercase_conversion(self):
        assert normalize_brand_name("BMW") == "bmw"
        assert normalize_brand_name("Mercedes") == "mercedes"

    def test_space_replacement(self):
        assert normalize_brand_name("Alfa Romeo") == "alfa-romeo"
        assert normalize_brand_name("Land Rover") == "land-rover"

    def test_underscore_replacement(self):
        assert normalize_brand_name("alfa_romeo") == "alfa-romeo"
        assert normalize_brand_name("land_rover") == "land-rover"

    def test_mixed_formatting(self):
        assert normalize_brand_name("Alfa Romeo") == "alfa-romeo"
        assert normalize_brand_name("ALFA_ROMEO") == "alfa-romeo"
        assert normalize_brand_name("Alfa_Romeo") == "alfa-romeo"

    def test_already_normalized(self):
        assert normalize_brand_name("bmw") == "bmw"
        assert normalize_brand_name("alfa-romeo") == "alfa-romeo"

    def test_multiple_spaces(self):
        assert normalize_brand_name("Land  Rover") == "land--rover"


@pytest.mark.unit
class TestEnsureDirectory:
    def test_creates_directory(self, tmp_path):
        test_dir = tmp_path / "test_folder"
        result = ensure_directory(str(test_dir))

        assert os.path.exists(test_dir)
        assert os.path.isdir(test_dir)
        assert result == str(test_dir)

    def test_creates_nested_directories(self, tmp_path):
        test_dir = tmp_path / "parent" / "child" / "grandchild"
        result = ensure_directory(str(test_dir))

        assert os.path.exists(test_dir)
        assert result == str(test_dir)

    def test_existing_directory(self, tmp_path):
        test_dir = tmp_path / "existing"
        test_dir.mkdir()

        result = ensure_directory(str(test_dir))
        assert os.path.exists(test_dir)
        assert result == str(test_dir)


@pytest.mark.unit
class TestLoadDealerBrandMapping:
    def test_load_valid_mapping(self, tmp_path, monkeypatch, sample_dealer_mapping):
        mapping_file = tmp_path / "dealer_brand_mapping.json"
        with open(mapping_file, 'w') as f:
            json.dump(sample_dealer_mapping, f)

        monkeypatch.setattr('sgcarmart.utils.file_utils.DEALER_BRAND_MAPPING_FILE', str(mapping_file))

        result = load_dealer_brand_mapping()
        assert result == sample_dealer_mapping
        assert len(result) == 4

    def test_load_empty_mapping(self, tmp_path, monkeypatch):
        mapping_file = tmp_path / "empty_mapping.json"
        with open(mapping_file, 'w') as f:
            json.dump({}, f)

        monkeypatch.setattr('sgcarmart.utils.file_utils.DEALER_BRAND_MAPPING_FILE', str(mapping_file))

        result = load_dealer_brand_mapping()
        assert result == {}


@pytest.mark.unit
class TestExtractMetadataFromUrl:
    def test_standard_pricelist_url(self):
        url = "https://www.sgcarmart.com/new_cars/pricelist/82/2025-01-15.pdf"
        metadata = extract_metadata_from_url(url)

        assert metadata['filename'] == "2025-01-15"
        assert metadata['dealer_id'] == "82"
        assert metadata['date'] == "2025-01-15"

    def test_url_without_dealer_id(self):
        url = "https://example.com/files/2025-01-15.pdf"
        metadata = extract_metadata_from_url(url)

        assert metadata['filename'] == "2025-01-15"
        assert metadata['dealer_id'] is None
        assert metadata['date'] == "2025-01-15"

    def test_relative_url(self):
        url = "/new_cars/pricelist/44/2024-12-20.pdf"
        metadata = extract_metadata_from_url(url)

        assert metadata['filename'] == "2024-12-20"
        assert metadata['dealer_id'] == "44"
        assert metadata['date'] == "2024-12-20"

    def test_url_with_trailing_slash(self):
        url = "https://www.sgcarmart.com/new_cars/pricelist/1/2025-02-01.pdf/"
        metadata = extract_metadata_from_url(url)

        assert metadata['filename'] == "2025-02-01"
        assert metadata['dealer_id'] == "1"
