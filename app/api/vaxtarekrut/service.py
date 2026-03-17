from __future__ import annotations
from typing import Any, List, Dict
from app.include.config import config
import httpx
from fastapi import HTTPException
import asyncio
import re
from bs4 import BeautifulSoup


VAXTAREKRUT_BASE_URL = "https://platform.vaxtarekrut.ru/api"
VAXTAREKRUT_PLACES_ENDPOINT = "/t_places"
VAXTAREKRUT_JOB_OFFERINGS_ENDPOINT = "/t_job_offerings"


# -------------------------------
# HTML очистка
# -------------------------------

def clean_html(text: str | None) -> str:
    if not text:
        return ""

    text = re.sub(r'<img[^>]+src="data:image[^"]+"[^>]*>', '', text)
    text = re.sub(r'<img[^>]*>', '', text)

    return text


def html_to_text(html: str | None) -> str:
    if not html:
        return ""

    html = clean_html(html)
    soup = BeautifulSoup(html, "html.parser")

    return soup.get_text("\n", strip=True)


# -------------------------------
# Форматирование вакансии
# -------------------------------

def format_job(job: dict) -> dict:
    description = html_to_text(job.get("f_offering_new_description"))

    return {
        "id": job.get("id"),
        "name": job.get("f_offering_name"),
        "salary_min": job.get("f_offering_min_price"),
        "salary_max": job.get("f_offering_max_price"),
        "men_needed": job.get("f_offering_men_needed"),
        "women_needed": job.get("f_offering_women_needed"),
        "age_min": job.get("f_min_age"),
        "age_max": job.get("f_offering_max_age"),
        "description": description
    }


# -------------------------------
# API вызовы
# -------------------------------

async def get_regions() -> dict[str, Any]:
    if not config.VAXTAREKRUT_API_KEY:
        raise HTTPException(status_code=400, detail="VAXTAREKRUT_API_KEY is required")

    url = f"{VAXTAREKRUT_BASE_URL}{VAXTAREKRUT_PLACES_ENDPOINT}"
    headers = {"Authorization": f"Bearer {config.VAXTAREKRUT_API_KEY}"}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Vaxtarekrut API error: {exc.response.text}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Vaxtarekrut request failed: {exc!s}") from exc

    data = response.json()
    return data if isinstance(data, dict) else {"data": data}


async def get_region_id_by_name(region_name: str) -> int:
    regions = await get_regions()
    items = regions.get("data", regions)

    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail="Unexpected regions response format")

    region_name_normalized = region_name.strip().lower()

    for item in items:
        if region_name_normalized in str(item.get("f_places_name", "")).strip().lower():
            return int(item["id"])

    raise HTTPException(status_code=404, detail=f"Region '{region_name}' not found")


async def get_job_offerings_by_filters(**kwargs: Any) -> dict[str, Any]:
    if not config.VAXTAREKRUT_API_KEY:
        raise HTTPException(status_code=400, detail="VAXTAREKRUT_API_KEY is required")

    region_name = kwargs.pop("region", None)
    if region_name:
        kwargs["f_778clr1gcvp"] = await get_region_id_by_name(region_name)

    params: dict[str, Any] = {}

    for field, value in kwargs.items():
        if isinstance(value, dict):
            for operator, operator_value in value.items():
                params[f"filter[{field}][{operator}]"] = operator_value
        else:
            params[f"filter[{field}]"] = value

    url = f"{VAXTAREKRUT_BASE_URL}{VAXTAREKRUT_JOB_OFFERINGS_ENDPOINT}"
    headers = {"Authorization": f"Bearer {config.VAXTAREKRUT_API_KEY}"}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Vaxtarekrut API error: {exc.response.text}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Vaxtarekrut request failed: {exc!s}") from exc

    data = response.json()
    return data if isinstance(data, dict) else {"data": data}


# -------------------------------
# Удобный поиск вакансий
# -------------------------------

async def find_jobs(
    region: str | None = None,
    men: bool | None = None,
    women: bool | None = None,
    min_salary: int | None = None,
    min_age: int | None = None,
    max_age: int | None = None,
) -> List[Dict]:

    filters: dict[str, Any] = {}

    if region:
        filters["region"] = region

    if men:
        filters["f_offering_men_needed"] = {"$gt": 0}

    if women:
        filters["f_offering_women_needed"] = {"$gt": 0}

    if min_salary:
        filters["f_offering_min_price"] = {"$gte": min_salary}

    if min_age:
        filters["f_min_age"] = {"$gte": min_age}

    if max_age:
        filters["f_offering_max_age"] = {"$lte": max_age}

    data = await get_job_offerings_by_filters(**filters)

    jobs = data.get("data", [])

    return [format_job(job) for job in jobs]


# -------------------------------
# Пример использования
# -------------------------------

if __name__ == "__main__":

    jobs = asyncio.run(
        find_jobs(
            region="Москва",
        )
    )

    for job in jobs:
        print("\n==============================")
        for k, v in job.items():
            print(f"{k}: {v}")