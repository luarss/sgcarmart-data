import random
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from constants import (
    USER_AGENTS,
    MAX_RETRIES,
    INITIAL_RETRY_DELAY,
)


class RateLimitException(Exception):
    pass


def get_random_user_agent():
    return random.choice(USER_AGENTS)


@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=INITIAL_RETRY_DELAY, min=INITIAL_RETRY_DELAY, max=60),
    retry=retry_if_exception_type(RateLimitException),
    reraise=True
)
def fetch_with_retry(url, timeout):
    headers = {"User-Agent": get_random_user_agent()}
    response = requests.get(url, headers=headers, timeout=timeout)

    if response.status_code == 429:
        raise RateLimitException("Rate limited")

    response.raise_for_status()
    return response
