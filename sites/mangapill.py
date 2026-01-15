import asyncio
import re
from typing import TYPE_CHECKING

import aiohttp
from bs4 import BeautifulSoup as bs

from .provider import Provider

if TYPE_CHECKING:
    import requests

BASE_URL = "https://mangapill.com"
INFO_URL = "https://mangapill.com/manga/{id}"

# CDN_URL = "https://cdn.readdetectiveconan.com"
# IMAGE_URL = CDN_URL + "/file/mangap/{id}/10{chapter_nr:03d}000/{file}"
# CHAPTER_URL = "https://mangapill.com/chapters/{id}-10{chapter_nr:03d}000"


class Mangapill(Provider):
    domain = "mangapill.com"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://mangapill.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    def __init__(self, session: "requests.Session", url) -> None:
        self.s = session
        self.id = self.parse_url(url)

    def parse_url(self, url: str) -> str:
        parse = re.search(r"manga\/(?P<id>\d+)", url)
        return parse.group("id") if parse else ""

    def get_url(self) -> str:
        return INFO_URL.format(id=self.id)

    @staticmethod
    def parse_info(payload: bs) -> dict:
        title_elem = payload.select_one("h1.font-bold")
        title = title_elem.get_text(strip=True) if title_elem else "Unknown Title"
        desc_p = payload.select_one("p.text-sm.text--secondary")
        description = None

        if desc_p:
            html_content = desc_p.decode_contents()
            if "<br><br>" in html_content:
                html_content = html_content.split("<br><br>", 1)[1]
            clean_soup = bs(html_content, "html.parser")
            text = clean_soup.get_text("\n", strip=True)
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            for i, line in enumerate(lines):
                if line.startswith("The "):
                    lines = lines[i:]
                    break
            description = "\n\n".join(lines) if lines else None

        genres = [
            a.get_text(strip=True) for a in payload.select("a[href^='/search?genre=']")
        ]

        return {
            "series": title,
            "genre": genres,
            "summary": description,
            "scanInformation": "MangaPill",
        }

    async def _fetch_chapter(
        self,
        session: aiohttp.ClientSession,
        href: str,
        title: str,
        nbr: float,
        semaphore: asyncio.Semaphore,
    ):
        """Internal async worker to fetch a single chapter's images."""
        async with semaphore:
            try:
                async with session.get(BASE_URL + href) as response:
                    content = await response.read()
                    soup = bs(content, "html.parser")

                    images = []
                    for img in soup.select("img.js-page"):
                        src = img.get("data-src") or img.get("src")
                        if src:
                            images.append(src)

                    return {"nr": nbr, "title": title, "images": images}
            except Exception:
                return {"nr": nbr, "title": title, "images": []}

    async def _async_get_all_chapters(self, chapter_tags: list) -> list:
        """Sets up the concurrent tasks and executes them."""
        semaphore = asyncio.Semaphore(25)  # Limits to 15 concurrent requests
        total_ch = len(chapter_tags)

        async with aiohttp.ClientSession(headers=self.headers) as session:
            tasks = []
            for i, a in enumerate(chapter_tags):
                chapter_title = a.get_text(strip=True)
                match = re.search(
                    r"Chapter\s*(?P<nbr>[\d.]+)", chapter_title, re.IGNORECASE
                )
                nbr = float(match.group("nbr")) if match else float(total_ch - i)

                tasks.append(
                    self._fetch_chapter(
                        session, a["href"], chapter_title, nbr, semaphore
                    )
                )

            return await asyncio.gather(*tasks)

    def get_mediainfo(self) -> tuple[dict, list]:

        r = self.s.get(self.get_url())
        series_page = bs(r.content, "html.parser")

        info = self.parse_info(series_page)

        raw_chapters = series_page.select("#chapters a[href^='/chapters/']")

        chapters = asyncio.run(self._async_get_all_chapters(raw_chapters))

        chapters.sort(key=lambda x: x["nr"])

        return info, chapters
