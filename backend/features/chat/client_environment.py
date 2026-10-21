"""Coarse, self-reported client families. No raw headers leave this pure normalizer."""
from dataclasses import dataclass
from collections.abc import Mapping
import re


@dataclass(frozen=True)
class ClientEnvironment:
    os_family: str
    browser_family: str
    os_source: str
    browser_source: str

    def public(self):
        return {'os_family': {'value': self.os_family, 'source': self.os_source},
                'browser_family': {'value': self.browser_family, 'source': self.browser_source},
                'reliability': 'best_effort', 'trust': 'client_reported'}


def _header(headers, name, limit):
    value = headers.get(name, '')
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
        return ''
    return value.strip()


def _ua_os(ua):
    if re.search(r'Windows Phone', ua, re.I):
        return 'unknown'
    for pattern, family in ((r'iPhone|iPad|iPod', 'ios'), (r'Android', 'android'), (r'CrOS', 'chromeos'),
                            (r'Windows NT', 'windows'), (r'Macintosh|Mac OS X', 'macos'), (r'Linux', 'linux')):
        if re.search(pattern, ua, re.I):
            return family
    return 'unknown'


def _ua_browser(ua):
    # Unsupported named browsers must not become Chrome just because they include its compatibility token.
    if re.search(r'SamsungBrowser/|Vivaldi/|DuckDuckGo/', ua, re.I):
        return 'unknown'
    for pattern, family in ((r'(?:Edg|EdgA|EdgiOS|Edge)/', 'edge'), (r'OPR/|Opera/|OPiOS/', 'opera'),
                            (r'Electron/|; wv\)|Chromium/', 'chromium'), (r'Firefox/|FxiOS/', 'firefox'),
                            (r'Chrome/|CriOS/', 'chrome')):
        if re.search(pattern, ua, re.I):
            return family
    return 'safari' if re.search(r'Version/[0-9]', ua) and 'Safari/' in ua else 'unknown'


def normalize(headers: Mapping[str, str] | None) -> ClientEnvironment:
    headers = headers if headers is not None else {}
    ua = _header(headers, 'user-agent', 1024)
    platform = _header(headers, 'sec-ch-ua-platform', 64)
    os_hint = {'"Windows"': 'windows', '"macOS"': 'macos', '"iOS"': 'ios', '"Android"': 'android',
               '"Chrome OS"': 'chromeos', '"Chromium OS"': 'chromeos', '"Linux"': 'linux'}.get(platform, 'unknown')
    brands = _header(headers, 'sec-ch-ua', 512)
    # Accept the bounded structured format, not arbitrary substrings or model-provided labels.
    brand_pattern = r'"([^"\\]{1,64})"\s*;\s*v="[0-9]{1,4}(?:\.[0-9]{1,4}){0,3}"'
    valid_brands = bool(re.fullmatch(r'\s*' + brand_pattern + r'(?:\s*,\s*' + brand_pattern + r')*\s*', brands))
    names = set(re.findall(brand_pattern, brands)) if valid_brands else set()
    known_brands = {'Microsoft Edge': 'edge', 'Google Chrome': 'chrome', 'Opera': 'opera', 'Opera GX': 'opera'}
    specific = {known_brands[name] for name in names if name in known_brands}
    ambiguous = len(specific) > 1
    browser_hint = next(iter(specific)) if len(specific) == 1 else 'chromium' if 'Chromium' in names else 'unknown'

    def resolve(hint, fallback, conflict=False):
        if conflict:
            return 'unknown', 'conflicting_client_headers'
        if hint != 'unknown':
            return hint, 'client_hint_normalized'
        return (fallback, 'user_agent_normalized') if fallback != 'unknown' else ('unknown', 'unavailable')

    ua_os, ua_browser = _ua_os(ua), _ua_browser(ua)
    os_family, os_source = resolve(os_hint, ua_os, os_hint != 'unknown' and ua_os != 'unknown' and os_hint != ua_os)
    # Chromium-family UA often only says Chrome. That generic compatibility token is not a contradiction.
    chromium = {'chrome', 'chromium', 'edge', 'opera'}
    browser_conflict = (browser_hint != 'unknown' and ua_browser != 'unknown' and browser_hint != ua_browser
                        and not (browser_hint in chromium and ua_browser in {'chrome', 'chromium'}))
    browser_family, browser_source = resolve(browser_hint, ua_browser, ambiguous or browser_conflict)
    return ClientEnvironment(os_family, browser_family, os_source, browser_source)
