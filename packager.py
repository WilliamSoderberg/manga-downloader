import zipfile
from pathlib import Path


def zip_files(slug, chapter: dict, files: list[Path], save_dir: Path):
    save_dir.joinpath(slug).mkdir(exist_ok=True)
    filename = save_dir.joinpath(slug).joinpath(f"{slug} Ch.{chapter.get('nr'):g}.cbz")  # type: ignore
    with zipfile.ZipFile(filename, "w") as zf:
        for file in files:
            zf.write(file, file.name)
        zf.close()

    return filename
