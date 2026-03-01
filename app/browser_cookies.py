"""
Browser cookie extraction for Skool Video Downloader.

Reads Skool session cookies directly from installed browsers
(Chrome, Firefox, Edge, Opera, Brave) so the user doesn't have
to manually copy them from DevTools.
"""

import logging

logger = logging.getLogger("skool_downloader")

SKOOL_DOMAIN = ".skool.com"

# Browser loader functions from browser_cookie3, in priority order.
_BROWSERS = [
    ("Chrome", "chrome"),
    ("Firefox", "firefox"),
    ("Edge", "edge"),
    ("Opera", "opera"),
    ("Brave", "brave"),
    ("Chromium", "chromium"),
]


def extract_skool_cookie() -> dict:
    """Try each installed browser and return the Skool cookie string.

    Returns a dict with:
      - "cookie": the full cookie header string (or "")
      - "browser": which browser it was found in (or "")
      - "error": error message if extraction failed (or "")
    """
    try:
        import browser_cookie3
    except ImportError:
        return {
            "cookie": "",
            "browser": "",
            "error": "browser_cookie3 is not installed. Run: pip install browser-cookie3",
        }

    errors = []

    for browser_name, func_name in _BROWSERS:
        loader = getattr(browser_cookie3, func_name, None)
        if loader is None:
            continue

        try:
            cj = loader(domain_name=SKOOL_DOMAIN)
            # Build the Cookie header string from all cookies for skool.com
            cookies = []
            for cookie in cj:
                if SKOOL_DOMAIN in (cookie.domain or ""):
                    cookies.append(f"{cookie.name}={cookie.value}")

            if cookies:
                cookie_str = "; ".join(cookies)
                logger.info(
                    "Found Skool cookie in %s (%d cookie parts)",
                    browser_name,
                    len(cookies),
                )
                return {
                    "cookie": cookie_str,
                    "browser": browser_name,
                    "error": "",
                }
        except Exception as e:
            errors.append(f"{browser_name}: {e}")
            logger.debug("Could not read cookies from %s: %s", browser_name, e)
            continue

    error_msg = "No Skool cookie found in any browser. Make sure you are logged into Skool."
    if errors:
        error_msg += " Errors: " + "; ".join(errors)

    return {"cookie": "", "browser": "", "error": error_msg}
