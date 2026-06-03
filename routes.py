import os

from aiohttp import web

import folder_paths
from server import PromptServer

from .common import safe_base_dir, safe_subdir

routes = PromptServer.instance.routes


@routes.get("/smartload/subfolders")
async def smartload_subfolders(request: web.Request) -> web.Response:
    """List immediate (single-level) subfolders of an allowed base folder."""
    base = request.rel_url.query.get("base", "")
    base_dir = safe_base_dir(base)
    if base_dir is None:
        return web.json_response({"error": "Invalid base folder"}, status=400)

    subfolders = []
    try:
        for entry in os.scandir(base_dir):
            if entry.is_dir() and not entry.name.startswith('.'):
                subfolders.append(entry.name)
    except FileNotFoundError:
        pass

    subfolders.sort(key=str.lower)
    return web.json_response(subfolders)


@routes.get("/smartload/images")
async def smartload_images(request: web.Request) -> web.Response:
    """List image files (newest first) in an allowed base/subfolder.

    Non-image files (e.g. videos) are filtered out via mimetype.
    """
    base = request.rel_url.query.get("base", "")
    subfolder = request.rel_url.query.get("subfolder", "")

    sub_dir = safe_subdir(base, subfolder)
    if sub_dir is None:
        return web.json_response({"error": "Invalid path"}, status=400)

    try:
        entries = [
            entry for entry in os.scandir(sub_dir)
            if entry.is_file() and not entry.name.startswith('.')
        ]
    except FileNotFoundError:
        return web.json_response([])

    image_names = set(folder_paths.filter_files_content_types(
        [entry.name for entry in entries], ["image"]
    ))

    sorted_entries = sorted(
        (entry for entry in entries if entry.name in image_names),
        key=lambda entry: -entry.stat().st_mtime,
    )
    return web.json_response([entry.name for entry in sorted_entries])
