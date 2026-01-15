import asyncio
import tempfile
import xml.etree.ElementTree as XML
from pathlib import Path

import aiofiles
import aiohttp
import questionary
from aiohttp import ClientError
from rich import print, status
from rich.progress import MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

from packager import zip_files
from sites import Provider


class Manga:
    def __init__(self, provider: Provider, cached: list[float] = []) -> None:
        self.site = provider
        self.cached = cached

        spinner = status.Status("Fetching manga info")
        spinner.start()
        self.info, self.chapters = self.site.get_mediainfo()
        spinner.stop()

        self.slug = self.slugify(self.info.get("series"))  # type: ignore

    @staticmethod
    def slugify(string: str) -> str:
        string = "".join(x for x in string if not x in '<>:"/\\|?*')
        return str(string)

    def _generateComicInfo(self, chapter: dict, dir: Path):
        filename = dir.joinpath("ComicInfo.xml")
        ComicInfo = XML.Element("ComicInfo")

        XML.SubElement(ComicInfo, "Series").text = self.info.get("series")
        XML.SubElement(ComicInfo, "Writer").text = ",".join(self.info.get("writer", []))  # type: ignore
        XML.SubElement(ComicInfo, "Penciller").text = ",".join(self.info.get("penciller", []))  # type: ignore
        XML.SubElement(ComicInfo, "Genre").text = ",".join(self.info.get("genre", []))  # type: ignore
        XML.SubElement(ComicInfo, "Summary").text = self.info.get("summary")
        XML.SubElement(ComicInfo, "Number").text = str(chapter.get("nr"))
        XML.SubElement(ComicInfo, "Title").text = chapter.get("title")
        XML.SubElement(ComicInfo, "LanguageISO").text = self.info.get("languageISO")
        XML.SubElement(ComicInfo, "PageCount").text = str(len(chapter.get("images")))  # type: ignore
        XML.SubElement(ComicInfo, "ScanInformation").text = self.info.get(
            "scanInformation"
        )

        tree = XML.ElementTree(ComicInfo)

        XML.indent(tree, space="\t", level=0)
        tree.write(str(filename), encoding="utf-8")

        return filename

    @staticmethod
    def printMangaInfo(info: dict):
        print(info)

    def choose_chapters(self, auto):
        choices = [
            questionary.Choice(
                f"{chapter.get('nr'):g}: {chapter.get('title')}",
                chapter,
                checked=chapter.get("nr") not in self.cached,
            )
            for chapter in self.chapters
        ]
        self.chapters = (
            questionary.checkbox("Choose which chapters to download", choices)
            .skip_if(
                auto,
                [
                    chapter
                    for chapter in self.chapters
                    if chapter.get("nr") not in self.cached
                ],
            )
            .ask()
        )

    def download(self, save_dir: Path):
        if not self.chapters:
            print("No new [orange3]Chapter[/] were found...")
            return

        async def process_all_chapters():

            chapter_sem = asyncio.Semaphore(8)
            image_sem = asyncio.Semaphore(40)

            connector = aiohttp.TCPConnector(limit=100, ttl_dns_cache=300)
            async with aiohttp.ClientSession(
                headers=self.site.headers, connector=connector
            ) as session:
                with Progress(
                    TextColumn("[progress.description]{task.description}"),
                    MofNCompleteColumn(),
                    SpinnerColumn(),
                ) as p:
                    task = p.add_task(
                        f"[bold]Processing [orange3]{self.info.get('series')}[/]",
                        total=len(self.chapters),
                    )

                    async def download_and_zip(chapter):
                        async with chapter_sem:
                            chapter_nr = chapter.get("nr")
                            chapter_temp = Path(temp_dir) / f"ch_{chapter_nr:g}"
                            chapter_temp.mkdir(parents=True, exist_ok=True)
                            info_file = self._generateComicInfo(chapter, chapter_temp)
                            img_urls = chapter.get("images", [])
                            img_files = await self._async_download_images_internal(
                                img_urls, chapter_temp, session, image_sem
                            )

                            all_files = [info_file] + [f for f in img_files if f]
                            zip_files(self.slug, chapter, all_files, save_dir)

                            self.cached.append(chapter_nr)
                            p.update(task, advance=1)

                    await asyncio.gather(
                        *(download_and_zip(ch) for ch in self.chapters)
                    )

        with tempfile.TemporaryDirectory(prefix="manga_") as temp_dir:
            asyncio.run(process_all_chapters())

    async def _async_download_images_internal(self, urls, temp_dir, session, semaphore):
        """Worker to manage the image download tasks for a single chapter."""

        async def bounded_download(url):
            async with semaphore:
                return await self.download_image(
                    session, url, temp_dir, self.site.headers
                )

        tasks = [bounded_download(url) for url in urls]
        return await asyncio.gather(*tasks)

    @staticmethod
    async def download_image(
        session: aiohttp.ClientSession,
        url: str,
        temp_dir: Path,
        headers: dict,
        retries=3,
        timeout=10,
    ):

        filename = temp_dir.joinpath(Path(url).name)

        for attempt in range(1, retries + 1):
            try:
                async with session.get(url, headers=headers, timeout=timeout) as response:  # type: ignore
                    if response.status == 200:
                        async with aiofiles.open(filename, "wb") as f:
                            await f.write(await response.read())
                        return filename
                    else:
                        raise ClientError(f"Bad status {response.status} for {url}")
            except (
                asyncio.TimeoutError,
                ClientError,
                aiohttp.ClientConnectorError,
            ) as e:
                if attempt < retries:
                    await asyncio.sleep(2**attempt)
                else:
                    print(f"Failed to download {url}: {e}")
                    return None
