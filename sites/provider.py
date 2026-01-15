from abc import ABC, abstractmethod


class Provider(ABC):

    domain: str
    headers: dict

    @abstractmethod
    def get_mediainfo(self) -> tuple[dict, list]:
        pass

    @abstractmethod
    def get_url(self) -> str:
        pass
