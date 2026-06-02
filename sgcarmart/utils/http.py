import random
import threading
import time

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from sgcarmart.constants import (
    CRAWL_DELAY_SECONDS,
    INITIAL_RETRY_DELAY,
    MAX_RETRIES,
    USER_AGENTS,
)


class RateLimitError(Exception):
    pass


_crawl_delay_lock = threading.Lock()
_last_request_time = None


def get_random_user_agent():
    return random.choice(USER_AGENTS)


def apply_crawl_delay():
    global _last_request_time

    with _crawl_delay_lock:
        if _last_request_time is not None:
            elapsed = time.time() - _last_request_time
            if elapsed < CRAWL_DELAY_SECONDS:
                sleep_time = CRAWL_DELAY_SECONDS - elapsed
                time.sleep(sleep_time)

        _last_request_time = time.time()


@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=INITIAL_RETRY_DELAY, min=INITIAL_RETRY_DELAY, max=60),
    retry=retry_if_exception_type(RateLimitError),
    reraise=True,
)
def fetch_with_retry(url, timeout, extra_headers=None):
    apply_crawl_delay()

    headers = {"User-Agent": get_random_user_agent()}
    if extra_headers:
        headers.update(extra_headers)
    response = requests.get(url, headers=headers, timeout=timeout)

    if response.status_code == 429:
        raise RateLimitError("Rate limited")

    response.raise_for_status()
    return response
