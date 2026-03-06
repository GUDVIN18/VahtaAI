from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp
from yarl import URL

from app.include.logging_config import logger as log


def _user_agent_for_source_agent(url: str) -> str:
    source_agent = dict(parse_qsl(urlsplit(url).query)).get("srcAg", "")
    mapping = {
        "CHROME_MAC": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "CHROME_IPHONE": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/123.0.0.0 Mobile/15E148 Safari/604.1"
        ),
        "SAFARI_IPHONE_OTHER": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
        ),
        "GECKO": (
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) "
            "Gecko/20100101 Firefox/124.0"
        ),
    }
    return mapping.get(
        source_agent,
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
    )


def _remove_query_key(url: str, key_to_remove: str) -> str:
    split = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(split.query, keep_blank_values=True) if key != key_to_remove]
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def _build_candidate_urls(base_url: str) -> list[str]:
    variants: list[str] = []
    for url in (base_url, _remove_query_key(base_url, "srcIp")):
        if url not in variants:
            variants.append(url)
    return variants


async def _download_to_file(session: aiohttp.ClientSession, url: str, file_path: Path) -> tuple[bool, str]:
    temp_path = file_path.with_suffix(file_path.suffix + ".part")
    request_url = URL(url, encoded=True)
    async with session.get(request_url, allow_redirects=True) as resp:
        if resp.status not in (200, 206):
            error_text = (await resp.text()).strip().replace("\n", " ")[:300]
            return False, f"status={resp.status}, body={error_text!r}"

        with temp_path.open("wb") as file:
            async for chunk in resp.content.iter_chunked(8192):
                file.write(chunk)

    temp_path.replace(file_path)
    return True, f"saved={file_path.name}"


async def download_voice(
    attach,
) -> Path | None:
    base_url = html.unescape(str(attach.url)).strip()
    file_path = f"app/api/vahta_ai/voice/upload/audio_{attach.audio_id}.mp3"
    file_path.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": _user_agent_for_source_agent(base_url),
        "Accept": "*/*",
        "Connection": "keep-alive",
        "Referer": "https://web.max.ru/",
        "Origin": "https://web.max.ru",
    }

    timeout = aiohttp.ClientTimeout(total=90)
    attempts = _build_candidate_urls(base_url)

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        for idx, url in enumerate(attempts, start=1):
            try:
                ok, details = await _download_to_file(session, url, file_path)
                if ok:
                    log.info(f"Аудио сохранено: {file_path} (attempt={idx})")
                    return file_path
                log.warning(f"Ошибка скачивания audio_id={attach.audio_id} (attempt={idx}): {details}")
            except Exception as exc:
                log.warning(f"Ошибка скачивания audio_id={attach.audio_id} (attempt={idx}): {exc}")

    part_file = file_path.with_suffix(file_path.suffix + ".part")
    if part_file.exists():
        part_file.unlink(missing_ok=True)
    return None
