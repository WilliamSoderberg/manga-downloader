from .flamecomics import FlameComics
from .provider import Provider

PROVIDERS = [
    FlameComics,
]


def parse_provider(session, url) -> Provider | None:
    for site in PROVIDERS:
        if site.domain() in url:
            return site(session, url)
