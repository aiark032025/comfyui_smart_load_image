import hashlib
import os

import numpy as np
import torch
from PIL import Image, ImageOps, ImageSequence

import comfy.model_management
import folder_paths  # noqa: F401  (imported for parity / future use)
import node_helpers

from .common import ALLOWED_BASES, NONE_LABEL, ROOT_LABEL, safe_annotated_path


class LoadImageSmart:
    """Load an image from a base folder (output/input) and an optional
    single-level subfolder.

    Improvements over the built-in Load Image nodes:
    - Videos (and other non-image files) are filtered out of the list.
    - Subfolders within the base folder are selectable.
    - A single node handles multiple base folders.
    - Selection is preserved across workflow reloads (frontend handles this).
    - An empty/missing selection returns a 1x1 placeholder image instead of
      raising, keeping the graph runnable.

    The ``image`` widget holds an annotated value ("[subfolder/]filename
    [type]") which is the authoritative selection and is resolved here. This
    matches the contract used by ComfyUI's mask editor, so it stays compatible.
    ``base_folder`` and ``subfolder`` are browse helpers used by the frontend
    to populate the image list; they are not used for path resolution.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_folder": (ALLOWED_BASES, {"default": ALLOWED_BASES[0]}),
                # subfolder/image options are populated by the frontend
                # extension; the lists declared here are intentionally minimal.
                "subfolder": ("COMBO", {"options": [ROOT_LABEL], "default": ROOT_LABEL}),
                "image": ("COMBO", {"options": [], "default": ""}),
            }
        }

    CATEGORY = "image"
    DESCRIPTION = (
        "Load an image from the output or input folder with base-folder and "
        "single-level subfolder selection. Non-image files (e.g. videos) are "
        "filtered out, and an empty selection returns a 1x1 placeholder image "
        "instead of erroring."
    )
    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "load_image"

    @staticmethod
    def _empty_image():
        # IMAGE is [B, H, W, C]; MASK is [B, H, W]. A single black pixel keeps
        # downstream nodes happy without raising on an empty selection.
        image = torch.zeros((1, 1, 1, 3), dtype=torch.float32)
        mask = torch.zeros((1, 1, 1), dtype=torch.float32)
        return (image, mask)

    def load_image(self, base_folder, subfolder, image):
        # Resolve from the authoritative annotated ``image`` value. base_folder
        # and subfolder are browse-only and intentionally unused here.
        image_path = safe_annotated_path(image)
        if image_path is None or not os.path.isfile(image_path):
            return self._empty_image()

        try:
            img = node_helpers.pillow(Image.open, image_path)
        except Exception:
            return self._empty_image()

        output_images = []
        output_masks = []
        w, h = None, None

        dtype = comfy.model_management.intermediate_dtype()

        for i in ImageSequence.Iterator(img):
            i = node_helpers.pillow(ImageOps.exif_transpose, i)

            if i.mode == 'I':
                i = i.point(lambda i: i * (1 / 255))
            image_rgb = i.convert("RGB")

            if len(output_images) == 0:
                w = image_rgb.size[0]
                h = image_rgb.size[1]

            if image_rgb.size[0] != w or image_rgb.size[1] != h:
                continue

            arr = np.array(image_rgb).astype(np.float32) / 255.0
            arr = torch.from_numpy(arr)[None,]
            if 'A' in i.getbands():
                mask = np.array(i.getchannel('A')).astype(np.float32) / 255.0
                mask = 1. - torch.from_numpy(mask)
            elif i.mode == 'P' and 'transparency' in i.info:
                mask = np.array(i.convert('RGBA').getchannel('A')).astype(np.float32) / 255.0
                mask = 1. - torch.from_numpy(mask)
            else:
                mask = torch.zeros((64, 64), dtype=torch.float32, device="cpu")
            output_images.append(arr.to(dtype=dtype))
            output_masks.append(mask.unsqueeze(0).to(dtype=dtype))

            if img.format == "MPO":
                break  # ignore all frames except the first one for MPO format

        if len(output_images) == 0:
            return self._empty_image()

        if len(output_images) > 1:
            output_image = torch.cat(output_images, dim=0)
            output_mask = torch.cat(output_masks, dim=0)
        else:
            output_image = output_images[0]
            output_mask = output_masks[0]

        return (output_image, output_mask)

    @classmethod
    def IS_CHANGED(cls, base_folder, subfolder, image):
        image_path = safe_annotated_path(image)
        if image_path is None or not os.path.isfile(image_path):
            # Empty selection is stable; vary so it re-runs once a file appears.
            return ""
        m = hashlib.sha256()
        with open(image_path, 'rb') as f:
            m.update(f.read())
        return m.digest().hex()

    @classmethod
    def VALIDATE_INPUTS(cls, base_folder, subfolder, image):
        # Declaring these parameter names bypasses the default combo-membership
        # check (the option lists are populated client-side), so we validate
        # the path ourselves instead.
        if base_folder not in ALLOWED_BASES:
            return "Invalid base folder: {}".format(base_folder)

        # An empty selection is allowed; the node returns a placeholder image.
        if image in (None, "", NONE_LABEL):
            return True

        image_path = safe_annotated_path(image)
        if image_path is None:
            return "Invalid image path: {}".format(image)
        if not os.path.isfile(image_path):
            return "Image not found: {}".format(image)
        return True
