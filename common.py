import os

import folder_paths

# Base folders the node is allowed to read from. To securely extend, add another
# directory type here that ``folder_paths.get_directory_by_type`` understands
# (e.g. "temp"). Everything else is validated against this allowlist.
ALLOWED_BASES = ["output", "input"]

# Sentinel used by the frontend combo to represent "the base folder itself"
# (no subfolder). Treated as an empty subfolder on the backend.
ROOT_LABEL = "(root)"

# Sentinel used by the frontend combo when a folder contains no images.
# Treated as "no selection" (returns a placeholder image) on the backend.
NONE_LABEL = "(no images)"


def is_allowed_base(base: str) -> bool:
    return base in ALLOWED_BASES


def normalize_subfolder(subfolder) -> str:
    if subfolder in (None, "", ROOT_LABEL):
        return ""
    return subfolder


def safe_base_dir(base: str):
    """Return the absolute base directory for an allowed base, else None."""
    if not is_allowed_base(base):
        return None
    directory = folder_paths.get_directory_by_type(base)
    if directory is None:
        return None
    return os.path.abspath(directory)


def safe_subdir(base: str, subfolder):
    """Resolve and validate a single-level subfolder inside an allowed base.

    Returns the absolute subfolder path, or None if the base/subfolder is
    invalid or would escape the base directory.
    """
    base_dir = safe_base_dir(base)
    if base_dir is None:
        return None

    subfolder = normalize_subfolder(subfolder)
    if subfolder:
        # Single path segment only: reject separators, traversal and absolutes.
        if (
            subfolder in (".", "..")
            or "/" in subfolder
            or "\\" in subfolder
            or os.path.isabs(subfolder)
        ):
            return None

    full = os.path.abspath(os.path.join(base_dir, subfolder))
    if os.path.commonpath([base_dir, full]) != base_dir:
        return None
    return full


def parse_annotated(value):
    """Parse an annotated image widget value into its parts.

    Mirrors the frontend ``parseImageWidgetValue`` contract:
        "[subfolder/]filename [type]"
    e.g. "cat.png [output]", "clipspace/clipspace-mask-1.png [input]".

    Returns a dict {type, subfolder, filename}, or None for empty values.
    Type defaults to "input" when no ``[type]`` suffix is present.
    """
    if not value:
        return None

    rest = value
    base_type = None
    if rest.endswith("]"):
        idx = rest.rfind(" [")
        if idx != -1:
            base_type = rest[idx + 2:-1]
            rest = rest[:idx]

    rest = rest.replace("\\", "/")
    subfolder = ""
    if "/" in rest:
        i = rest.rfind("/")
        subfolder = rest[:i]
        filename = rest[i + 1:]
    else:
        filename = rest

    return {"type": base_type or "input", "subfolder": subfolder, "filename": filename}


def safe_annotated_path(value):
    """Resolve and validate an annotated image value to an absolute file path.

    This is the authoritative resolver used by the node (and is compatible with
    the mask editor, which writes values like "clipspace/...[input]"). Returns
    None for empty/placeholder values or unsafe paths.
    """
    if value in (None, "", NONE_LABEL):
        return None

    ref = parse_annotated(value)
    if ref is None:
        return None

    base_type = ref["type"]
    if base_type not in ALLOWED_BASES:
        return None

    base_dir = safe_base_dir(base_type)
    if base_dir is None:
        return None

    rel = ref["subfolder"] + "/" + ref["filename"] if ref["subfolder"] else ref["filename"]
    rel = rel.replace("\\", "/")
    if rel.startswith("/") or os.path.isabs(rel):
        return None

    parts = [p for p in rel.split("/") if p != ""]
    if any(p in (".", "..") for p in parts):
        return None

    full = os.path.abspath(os.path.join(base_dir, *parts))
    if os.path.commonpath([base_dir, full]) != base_dir:
        return None
    return full
