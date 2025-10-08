import os
import json

from constants import DEALER_BRAND_MAPPING_FILE


def normalize_brand_name(brand):
    return brand.lower().replace(" ", "-").replace("_", "-")


def ensure_directory(path):
    os.makedirs(path, exist_ok=True)
    return path


def load_dealer_brand_mapping():
    with open(DEALER_BRAND_MAPPING_FILE, 'r') as f:
        return json.load(f)


def extract_metadata_from_url(pdf_url):
    parts = pdf_url.rstrip('/').split('/')
    filename = parts[-1].replace('.pdf', '')
    dealer_id = None

    if 'pricelist' in pdf_url:
        pricelist_index = parts.index('pricelist')
        if pricelist_index + 1 < len(parts):
            dealer_id = parts[pricelist_index + 1]

    return {
        'filename': filename,
        'dealer_id': dealer_id,
        'date': filename
    }
