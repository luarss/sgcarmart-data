import random

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from sgcarmart.constants import (
    INITIAL_RETRY_DELAY,
    MAX_RETRIES,
    USER_AGENTS,
)


class RateLimitError(Exception):
    pass


def get_random_user_agent():
    return random.choice(USER_AGENTS)


@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=INITIAL_RETRY_DELAY, min=INITIAL_RETRY_DELAY, max=60),
    retry=retry_if_exception_type(RateLimitError),
    reraise=True,
)
def fetch_with_retry(url, timeout, extra_headers=None):
    headers = {"User-Agent": get_random_user_agent()}
    if extra_headers:
        headers.update(extra_headers)
    response = requests.get(url, headers=headers, timeout=timeout)

    if response.status_code == 429:
        raise RateLimitError("Rate limited")

    response.raise_for_status()
    return response
