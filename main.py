import argparse
import configparser
import json
from pathlib import Path

import questionary
import requests
from manga import Manga
from rich import print
from sites import parse_provider

parser = argparse.ArgumentParser(
    prog="Manga Downloader",
    description="Download all your favourite manga!",
    epilog="Happy Reading!",
)
parser.add_argument(
    "--auto",
    default=False,
    action=argparse.BooleanOptionalAction,
    help="Run using auto mode (default: %(default)s)",
)
parser.add_argument(
    "--save-dir",
    dest="save_dir",
    type=Path,
    help="Set temporary save dir instead of using config value",
)

args = parser.parse_args()

s = requests.session()
cache_file = Path(__file__).parent.resolve().joinpath("manga.json")
config_file = Path(__file__).parent.resolve().joinpath("config.ini")


def get_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    if config_file.exists():
        config.read(config_file)

    if not config.has_option("DEFAULT", "savedir"):
        path = questionary.path(
            "Enter default save path for downloaded Manga: ", qmark=""
        ).ask()
        config["DEFAULT"] = {"savedir": path}

        with open(config_file, "w") as cf:
            config.write(cf)

    return config


def read_from_cache() -> dict:
    if cache_file.exists():
        return json.loads(cache_file.read_bytes())
    else:
        return {}


def write_to_cache(manga: Manga) -> None:
    cache = read_from_cache()
    series = manga.info.get("series")
    cached_chapters = cache.get(series, {}).get("cached", []) + manga.cached

    cache[series] = {"url": manga.site.get_url(), "cached": list(set(cached_chapters))}

    with open(cache_file, "w") as fp:
        json.dump(cache, fp, indent=4)


def parse_cache(cache: dict) -> list[Manga]:
    if not cache:
        print("Cache is empty!")
        exit()
    else:
        manga = list()
        for entry in cache.values():
            manga.append(
                Manga(parse_provider(s, entry.get("url")), entry.get("cached"))  # type: ignore
            )
        return manga


def get_cached_manga() -> list[Manga]:
    cache = read_from_cache()
    return parse_cache(cache)


def input_manga() -> list[str]:
    manga = list()
    add_more = True
    while add_more:
        manga.append(questionary.text("Input Manga url:", qmark="").ask())
        add_more = questionary.confirm(
            "Do you want to add more Manga", default=False
        ).ask()

    return manga


def parse_manga(manga: list[str]) -> list[Manga]:
    parsed_manga = list()
    for entry in manga:
        provider = parse_provider(s, entry)
        if not provider:
            print(f"Failed to parse: {entry}")
        else:
            parsed_manga.append(Manga(provider))
    return parsed_manga


def choose_manga() -> list[Manga]:
    use_cached = questionary.confirm(
        "Do you want to choose from cached Manga", default=True
    ).ask()

    if use_cached:
        return get_cached_manga()
    else:
        manga = input_manga()
        return parse_manga(manga)


def main():

    config = get_config()
    save_dir = args.save_dir if args.save_dir else Path(config["DEFAULT"]["savedir"])

    if args.auto:
        if not config_file.exists():
            print("No config file exists")
            exit(1)
        else:
            list_of_manga = get_cached_manga()
    else:
        list_of_manga = choose_manga()

    for manga in list_of_manga:
        manga.choose_chapters(args.auto)
        manga.download(save_dir)
        write_to_cache(manga)


if __name__ == "__main__":
    main()
