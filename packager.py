import asyncio
import zipfile
from pathlib import Path

import aiofiles
import aiohttp
from aiohttp import ClientError


async def download_image(
    session: aiohttp.ClientSession, url: str, temp_dir: Path, retries=3, timeout=10
):

    filename = temp_dir.joinpath(Path(url).name)

    for attempt in range(1, retries + 1):
        try:
            async with session.get(url, timeout=timeout) as response:  # type: ignore
                if response.status == 200:
                    async with aiofiles.open(filename, "wb") as f:
                        await f.write(await response.read())
                    return filename
                else:
                    raise ClientError(f"Bad status {response.status} for {url}")
        except (asyncio.TimeoutError, ClientError, aiohttp.ClientConnectorError) as e:
            if attempt < retries:
                await asyncio.sleep(2**attempt)
            else:
                print(f"Failed to download {url}: {e}")
                return None


async def _download_images(urls, temp_dir: Path, concurrency=5):
    semaphore = asyncio.Semaphore(concurrency)

    async with aiohttp.ClientSession() as session:

        async def bounded_download(url):
            async with semaphore:
                return await download_image(session, url, temp_dir)

        tasks = [bounded_download(url) for url in urls]
        return await asyncio.gather(*tasks)


def download_images(images: list[str], temp_dir: Path):
    return asyncio.run(_download_images(images, temp_dir))


def zip_files(slug, chapter: dict, files: list[Path], save_dir: Path):
    save_dir.joinpath(slug).mkdir(exist_ok=True)
    filename = save_dir.joinpath(slug).joinpath(f"{slug} - Ch. {chapter.get('nr')}.cbz")  # type: ignore
    with zipfile.ZipFile(filename, "w") as zf:
        for file in files:
            zf.write(file, file.name)
        zf.close()

    return filename
