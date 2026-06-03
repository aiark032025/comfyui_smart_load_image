# ComfyUI Smart Load Image

A single custom node, **Load Image (Smart)**, that addresses several shortcomings of
ComfyUI's built-in image loaders.

## Features

- **Base folder selector** – choose between `output` and `input` (easily extensible).
- **Subfolder selector** – lists single-level subfolders of the selected base folder;
  defaults to the base folder root (`(root)`).
- **Videos filtered out** – the image list only shows files whose mimetype is an image.
- **Single Refresh button** – re-reads the current base/subfolder for new files while
  keeping your current selection if it still exists.
- **Single Upload button** – behaves like the built-in Load Image upload; uploads the
  chosen image into the currently selected base/subfolder and selects it.
- **Selection survives reloads** – unlike the built-in remote combo, the saved selection
  is preserved when a workflow is reloaded or refreshed (no clobbering to the newest file).
- **Empty-safe** – if nothing is selected or the folder has no images, the node returns a
  1x1 placeholder image instead of raising.

## Architecture

- `nodes.py` – the `LoadImageSmart` node (path resolution, image loading, validation).
- `routes.py` – secure read-only APIs: `/smartload/subfolders` and `/smartload/images`.
- `common.py` – shared allowlist + path-safety helpers.
- `web/loadImageSmart.js` – frontend extension wiring the combos, refresh/upload buttons,
  preview, and the reload-safe value preservation.

Uploads reuse ComfyUI's existing, secured `POST /upload/image` endpoint.

## Extending the allowed base folders

Edit `ALLOWED_BASES` in `common.py` (and the matching list is fetched dynamically on the
frontend). Any value added must be understood by `folder_paths.get_directory_by_type`
(e.g. `"temp"`). All access remains validated against this allowlist with `commonpath`
containment checks.
