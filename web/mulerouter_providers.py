"""
MuleRouter providers aligned with the running SeedreamBest configuration.

SeedreamBest production env uses:
- Image provider: https://api.mulerouter.ai, model wan2.6-t2i
- Video provider: https://api.mulerouter.ai, model wan2.7-i2v-spicy

The image routing mirrors SeedreamBest's backend:
- text-to-image: carrothub/z-image-spicy
- image edit/reference: carrothub/qwen-image-edit-spicy
"""

from __future__ import annotations

import base64
import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx


MULEROUTER_BASE_URL = os.environ.get(
    "SEEDREAMBEST_IMAGE_PROVIDER_BASE_URL",
    os.environ.get("MULEROUTER_BASE_URL", "https://api.mulerouter.ai"),
)
MULEROUTER_IMAGE_MODEL = os.environ.get(
    "SEEDREAMBEST_IMAGE_PROVIDER_MODEL",
    os.environ.get("MULEROUTER_IMAGE_MODEL", "wan2.6-t2i"),
)
MULEROUTER_VIDEO_MODEL = os.environ.get(
    "SEEDREAMBEST_VIDEO_PROVIDER_MODEL",
    os.environ.get("MULEROUTER_VIDEO_MODEL", "wan2.7-i2v-spicy"),
)

Z_IMAGE_SPICY_RATIO_SIZE_MAP: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "4:3": (1365, 1024),
    "3:4": (1024, 1365),
    "16:9": (1536, 864),
    "9:16": (864, 1536),
    "3:2": (1536, 1024),
    "2:3": (1024, 1536),
}


@dataclass
class MuleRouterVideoResult:
    video_url: str
    status: str
    task_id: str = ""
    raw: Optional[dict[str, Any]] = None


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _provider_url(base_url: str, vendor: str, endpoint: str) -> str:
    return f"{base_url.rstrip('/')}/vendors/{vendor}/v1/{endpoint}/generation"


def _local_image_to_data_url(image_path: str) -> str:
    mime_type = mimetypes.guess_type(image_path)[0] or "image/png"
    data = Path(image_path).read_bytes()
    return f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"


def _normalize_image_inputs(images: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for image in images or []:
        if not image:
            continue
        if image.startswith(("http://", "https://", "data:")):
            normalized.append(image)
        elif os.path.exists(image):
            normalized.append(_local_image_to_data_url(image))
    return normalized


def _dimensions_for_ratio(ratio: str) -> tuple[int, int]:
    return Z_IMAGE_SPICY_RATIO_SIZE_MAP.get(ratio, Z_IMAGE_SPICY_RATIO_SIZE_MAP["3:2"])


def _extract_image_urls(data: dict[str, Any]) -> list[str]:
    images = data.get("images") or data.get("image_urls") or []
    if isinstance(images, str):
        return [images]
    if isinstance(images, list):
        urls: list[str] = []
        for item in images:
            if isinstance(item, str):
                urls.append(item)
            elif isinstance(item, dict):
                url = item.get("url") or item.get("image_url") or item.get("image")
                if url:
                    urls.append(str(url))
        if urls:
            return urls

    image = data.get("image") or data.get("image_url") or data.get("url")
    if image:
        return [str(image)]
    return []


async def generate_wan_image(
    *,
    api_key: str,
    prompt: str,
    images: list[str] | None = None,
    base_url: str = MULEROUTER_BASE_URL,
    ratio: str = "16:9",
    output_count: int = 1,
    timeout: float = 900.0,
) -> list[dict[str, Any]]:
    """Generate image(s) through MuleRouter using SeedreamBest's routing."""
    normalized_images = _normalize_image_inputs(images)
    if normalized_images:
        vendor = "carrothub"
        endpoint = "qwen-image-edit-spicy"
        payload: dict[str, Any] = {
            "prompt": prompt[:2000],
            "image": normalized_images[0],
        }
        input_images = normalized_images[:3]
        task_payloads = [
            {**payload, "image": input_images[index % len(input_images)]}
            for index in range(max(1, min(output_count, 15)))
        ]
    else:
        vendor = "carrothub"
        endpoint = "z-image-spicy"
        width, height = _dimensions_for_ratio(ratio)
        payload = {
            "prompt": prompt[:2000],
            "width": width,
            "height": height,
            "prompt_extend": True,
        }
        task_payloads = [{**payload} for _ in range(max(1, min(output_count, 15)))]

    create_url = _provider_url(base_url, vendor, endpoint)
    headers = _headers(api_key)
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=30.0)) as client:
        task_ids: dict[str, int] = {}
        for index, task_payload in enumerate(task_payloads):
            response = await client.post(create_url, headers=headers, json=task_payload)
            response.raise_for_status()
            task_info = response.json().get("task_info") or {}
            task_id = task_info.get("id")
            if not task_id:
                raise RuntimeError(f"MuleRouter image provider did not return task id: {response.text[:500]}")
            task_ids[str(task_id)] = index

        deadline = time.monotonic() + timeout
        pending = set(task_ids)
        results: list[dict[str, Any]] = []

        while pending:
            if time.monotonic() > deadline:
                raise TimeoutError("MuleRouter image generation timed out.")

            for task_id in list(pending):
                result_response = await client.get(f"{create_url}/{task_id}", headers={"Authorization": headers["Authorization"]})
                result_response.raise_for_status()
                data = result_response.json()
                status = str((data.get("task_info") or {}).get("status") or data.get("status") or "").lower()

                if status in {"completed", "succeeded"}:
                    for image_url in _extract_image_urls(data):
                        results.append({"url": image_url})
                    pending.remove(task_id)
                    continue

                if status in {"failed", "expired", "cancelled"}:
                    error = (data.get("task_info") or {}).get("error") or data.get("error") or data
                    raise RuntimeError(str(error)[:1000])

            if pending:
                await _sleep_async(3)

    if not results:
        raise RuntimeError("MuleRouter image provider did not return image URLs.")
    return results


async def create_wan_video(
    *,
    api_key: str,
    prompt: str,
    images: list[str] | None = None,
    model: str = MULEROUTER_VIDEO_MODEL,
    base_url: str = MULEROUTER_BASE_URL,
    ratio: str = "16:9",
    duration: int = 5,
    resolution: str = "1080p",
    generate_audio: bool = True,
    timeout: float = 1200.0,
) -> MuleRouterVideoResult:
    """Create and poll Wan video through MuleRouter."""
    normalized_images = _normalize_image_inputs(images)
    if normalized_images:
        vendor = "carrothub" if model == "wan2.7-i2v-spicy" else "alibaba"
        endpoint = "wan2.7-i2v-spicy" if model == "wan2.7-i2v-spicy" else "wan2.6-i2v"
        payload: dict[str, Any] = {
            "prompt": (prompt or "Generate a smooth, natural video.").strip()[:2000],
            "image": normalized_images[0],
            "resolution": "720p" if str(resolution).lower() == "720p" else "1080p",
            "duration": max(2, min(int(duration or 5), 15)),
            "prompt_extend": True,
        }
        if len(normalized_images) >= 2:
            payload["last_frame"] = normalized_images[1]
    else:
        vendor = "alibaba"
        endpoint = "wan2.6-t2v"
        payload = {
            "prompt": (prompt or "Generate a smooth, natural video.").strip()[:2000],
            "duration": 5 if int(duration or 5) <= 5 else 10,
            "prompt_extend": True,
            "shot_type": "single",
            "audio": bool(generate_audio),
            "safety_filter": True,
            "size": _t2v_size(ratio=ratio, resolution=resolution),
        }

    create_url = _provider_url(base_url, vendor, endpoint)
    headers = _headers(api_key)
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=15.0, read=120.0, write=30.0, pool=30.0)) as client:
        response = await client.post(create_url, headers=headers, json=payload)
        response.raise_for_status()
        create_data = response.json()
        task_info = create_data.get("task_info") or {}
        task_id = task_info.get("id")
        if not task_id:
            raise RuntimeError(f"MuleRouter video provider did not return task id: {str(create_data)[:500]}")

        deadline = time.monotonic() + timeout
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("MuleRouter video generation timed out.")

            result_response = await client.get(f"{create_url}/{task_id}", headers={"Authorization": headers["Authorization"]})
            result_response.raise_for_status()
            data = result_response.json()
            status = str((data.get("task_info") or {}).get("status") or data.get("status") or "").lower()

            if status in {"completed", "succeeded"}:
                video_url = _extract_video_url(data)
                if not video_url:
                    raise RuntimeError(f"MuleRouter video succeeded without URL: {str(data)[:500]}")
                return MuleRouterVideoResult(video_url=video_url, status=status, task_id=task_id, raw=data)

            if status in {"failed", "expired", "cancelled"}:
                error = (data.get("task_info") or {}).get("error") or data.get("error") or data
                raise RuntimeError(str(error)[:1000])

            await _sleep_async(5)


def _t2v_size(*, ratio: str, resolution: str) -> str:
    ratio = ratio if ratio != "adaptive" else "16:9"
    sizes_720 = {
        "16:9": "1280*720",
        "9:16": "720*1280",
        "1:1": "960*960",
        "4:3": "1088*832",
        "3:4": "832*1088",
    }
    sizes_1080 = {
        "16:9": "1920*1080",
        "9:16": "1080*1920",
        "1:1": "1440*1440",
        "4:3": "1632*1248",
        "3:4": "1248*1632",
    }
    size_map = sizes_1080 if str(resolution).lower() == "1080p" else sizes_720
    return size_map.get(ratio, size_map["16:9"])


def _extract_video_url(data: dict[str, Any]) -> str | None:
    videos = data.get("videos") or []
    if videos:
        return str(videos[0])
    output = data.get("output") or {}
    if isinstance(output, dict):
        output_videos = output.get("videos") or []
        if output_videos:
            return str(output_videos[0])
        if output.get("video_url"):
            return str(output["video_url"])
    content = data.get("content") or {}
    if isinstance(content, dict) and content.get("video_url"):
        return str(content["video_url"])
    if data.get("video"):
        return str(data["video"])
    return None


async def _sleep_async(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
