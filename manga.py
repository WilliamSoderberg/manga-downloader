import tempfile
import xml.etree.ElementTree as XML
from pathlib import Path

import questionary
from packager import download_images, zip_files
from rich import print
from rich.progress import MofNCompleteColumn, Progress, SpinnerColumn, TextColumn
from sites import Provider


class Manga:
    def __init__(self, provider: Provider, cached: list[int] = []) -> None:
        self.site = provider
        self.cached = cached
        self.info, self.chapters = self.site.get_mediainfo()
        self.slug = self.slugify(self.info.get("series"))  # type: ignore

    @staticmethod
    def slugify(string: str) -> str:
        string = "".join(x for x in string if not x in '<>:"/\\|?*')
        return str(string)

    def _generateComicInfo(self, chapter: dict, dir: Path):
        filename = dir.joinpath("ComicInfo.xml")
        ComicInfo = XML.Element("ComicInfo")

        XML.SubElement(ComicInfo, "Series").text = self.info.get("series")
        XML.SubElement(ComicInfo, "Writer").text = ",".join(self.info.get("writer"))  # type: ignore
        XML.SubElement(ComicInfo, "Penciller").text = ",".join(self.info.get("penciller"))  # type: ignore
        XML.SubElement(ComicInfo, "Genre").text = ",".join(self.info.get("genre"))  # type: ignore
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
                f"{chapter.get('nr'):02d}: {chapter.get('title')}",
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
        with tempfile.TemporaryDirectory(prefix="manga_") as temp_dir:
            if self.chapters:
                with Progress(
                    TextColumn("[progress.description]{task.description}"),
                    MofNCompleteColumn(),
                    SpinnerColumn(),
                ) as p:
                    task = p.add_task(
                        f"[bold]Processing [orange3]{self.info.get('series')}[/]",
                        total=len(self.chapters),
                    )
                    while not p.finished:
                        for chapter in self.chapters:
                            print(
                                f"Downloading [bold blue]Chapter {chapter.get('nr'):02d}[/]..."
                            )
                            files = [self._generateComicInfo(chapter, Path(temp_dir))]
                            files.extend(download_images(chapter.get("images"), Path(temp_dir)))  # type: ignore
                            zip_files(self.slug, chapter, files, save_dir)
                            self.cached.append(chapter.get("nr"))
                            p.update(task, advance=1)
            else:
                print("No new [orange3]Chapter[/] were found...")
