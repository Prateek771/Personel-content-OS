"""Exact URL normalization and canonical hashing."""

import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


def normalize_url(url: str) -> str:
    """Normalize URL by stripping tracking parameters, lowercase domain, and trailing slashes."""
    parsed = urlparse(url.strip())
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")

    # Strip marketing tracking queries
    tracking_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "fbclid", "gclid"}
    query_items = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in tracking_params]
    query_items.sort()
    clean_query = urlencode(query_items)

    return urlunparse((parsed.scheme.lower(), netloc, path, parsed.params, clean_query, ""))
