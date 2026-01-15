from .flamecomics import FlameComics
from .mangapill import Mangapill
from .provider import Provider

PROVIDERS = [FlameComics, Mangapill]


def parse_provider(session, url) -> Provider | None:
    for site in PROVIDERS:
        if site.domain in url:
            return site(session, url)
