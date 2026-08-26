"""
Small shared helper for making HTTP requests that survive flaky free APIs.

Both the Overpass API (OpenStreetMap) and the Companies House API can return
429 (rate limited) or 5xx (server busy/timeout) responses under normal use -
this is expected on free, shared infrastructure, not a bug. Instead of every
script re-implementing retry logic, they all call `request_with_retry()`.
"""

import time
import requests

# Status codes worth retrying. 429 = rate limited, the 5xx codes mean the
# server had a transient problem - retrying after a short wait usually works.
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Overpass's server (Apache + mod_security) returns 406 Not Acceptable for
# requests using the default "python-requests/x.x" User-Agent - it wants
# something that identifies the client. We send this on every request so
# both APIs see a well-behaved, identifiable client.
DEFAULT_USER_AGENT = "leadgen-tool/1.0 (personal lead-gen script; free/non-commercial use)"


def request_with_retry(method, url, max_retries=5, backoff_base=2, timeout=60, **kwargs):
    """
    Wrapper around requests.request() with exponential backoff.

    - method/url: same as requests.request()
    - max_retries: how many attempts before giving up
    - backoff_base: wait time doubles each retry (backoff_base ** attempt seconds)
    - timeout: per-request timeout in seconds
    - **kwargs: passed straight through to requests.request() (params, data, auth, ...)

    Returns the final `requests.Response` on success. Raises if every retry
    is exhausted (either the last HTTP error, or the last connection error).
    """
    headers = {"User-Agent": DEFAULT_USER_AGENT, **kwargs.pop("headers", {})}

    last_exc = None
    last_response = None

    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, timeout=timeout, headers=headers, **kwargs)
        except requests.exceptions.RequestException as exc:
            # Network-level failure (DNS, connection reset, timeout, ...).
            last_exc = exc
            wait = backoff_base ** attempt
            print(f"  Request error ({exc}); retrying in {wait:.0f}s...")
            time.sleep(wait)
            continue

        if response.status_code in RETRYABLE_STATUS_CODES:
            last_response = response
            # Some servers tell us exactly how long to wait - respect that
            # if it's present, otherwise fall back to our own backoff.
            retry_after = response.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else backoff_base ** attempt
            print(f"  Got HTTP {response.status_code} from {url}; retrying in {wait:.0f}s...")
            time.sleep(wait)
            continue

        return response

    if last_response is not None:
        last_response.raise_for_status()
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"Failed to get a response from {url} after {max_retries} attempts")
