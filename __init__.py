from .nodes import LoadImageSmart
from . import routes  # noqa: F401  (registers the /smartload/* API routes)

NODE_CLASS_MAPPINGS = {
    "LoadImageSmart": LoadImageSmart,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadImageSmart": "Load Image (Smart)",
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
