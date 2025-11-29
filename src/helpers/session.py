# src/helpers/session.py
from __future__ import annotations

import json
import os
import time
from typing import Dict
from urllib.parse import urlparse

# Helper functions for saving/loading browser cookies to persist sessions.
# Cookies are stored as JSON files under ./sessions/ (one file per email by default).
#
# Usage:
#   save_cookies_to_file(driver, cookie_path)
#   load_cookies_from_file_and_apply(driver, cookie_path, target_url)
#
# Notes:
# - Selenium requires you to navigate to the cookie's domain before calling add_cookie.
# - We filter out any attributes that aren't JSON-serializable or not accepted by add_cookie.
# - This module is defensive: failures do not raise, they just return False and log the reason.
# - Cookie expiry times are preserved when present.

ACCEPTED_COOKIE_KEYS = {
    "name",
    "value",
    "path",
    "domain",
    "secure",
    "expiry",
    "httpOnly",
    "sameSite",
}


def _sanitize_cookie_for_storage(cookie: Dict) -> Dict:
    """Return a JSON-serializable dict for the cookie by keeping only accepted keys."""
    sanitized = {}
    for k, v in cookie.items():
        if k in ACCEPTED_COOKIE_KEYS:
            # Selenium writes expiry as int, but some drivers may use float; ensure int or omit.
            if k == "expiry":
                try:
                    sanitized[k] = int(v)
                except Exception:
                    # omit invalid expiry
                    continue
            else:
                sanitized[k] = v
    return sanitized


def save_cookies_to_file(driver, file_path: str) -> bool:
    """
    Save current browser cookies to file_path (JSON).
    Returns True on success, False otherwise.
    """
    try:
        cookies = driver.get_cookies()
    except Exception:
        # Could not retrieve cookies (driver problem); silently return False
        return False

    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        sanitized = [_sanitize_cookie_for_storage(c) for c in cookies]
        # write atomically
        tmp = file_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sanitized, f, ensure_ascii=False, indent=2)
        os.replace(tmp, file_path)
        return True
    except Exception:
        return False


def _normalize_domain_for_nav(url: str) -> str:
    """
    Return scheme://netloc for a given URL so we can navigate to the host before setting cookies.
    """
    p = urlparse(url)
    scheme = p.scheme or "https"
    netloc = p.netloc
    return f"{scheme}://{netloc}"


def load_cookies_from_file_and_apply(driver, file_path: str, example_url: str) -> bool:
    """
    Load cookies from file_path and apply them to the browser driver.
    example_url is used to determine the domain to navigate to before adding cookies.
    Returns True if cookies were loaded & applied (no guarantee they're valid), False otherwise.
    """
    if not os.path.isfile(file_path):
        return False

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
    except Exception:
        return False

    if not isinstance(cookies, list) or not cookies:
        return False

    # Navigate to the base domain first so add_cookie works.
    base = _normalize_domain_for_nav(example_url)
    try:
        driver.get(base)
    except Exception:
        # If navigate fails, we still attempt to add cookies; but usually navigation is required.
        pass

    added_any = False
    for c in cookies:
        # make sure cookie has the minimal required keys
        name = c.get("name")
        value = c.get("value")
        if not name or value is None:
            continue
        # Build cookie dict acceptable by Selenium's add_cookie
        cookie_to_add = {}
        for k in (
            "name",
            "value",
            "path",
            "domain",
            "secure",
            "httpOnly",
            "expiry",
            "sameSite",
        ):
            if k in c:
                cookie_to_add[k] = c[k]
        try:
            # Selenium expects 'httpOnly' key as 'httpOnly' and 'sameSite' may vary; ignore invalid values
            driver.add_cookie(cookie_to_add)
            added_any = True
        except Exception:
            # ignore individual cookie failures
            continue

    # Finally a short pause so cookie takes effect when navigating next
    try:
        time.sleep(0.2)
    except Exception:
        pass

    return added_any
