"""Image processing service — compression and thumbnail generation.

All uploaded images (food photos, profile photos, receipts) should go
through this service to keep storage small and page loads fast.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Max dimensions for different image types
_SIZES = {
    'full': (1200, 1200),   # Max size for the "original" — still compressed
    'thumb': (400, 400),    # Thumbnail for lists/cards
    'micro': (80, 80),      # Tiny icon (profile avatars)
}


def process_image(input_path: str, output_dir: str, base_name: str,
                  sizes: list = None, quality: int = 80) -> dict:
    """Compress and resize an image, creating multiple variants.

    Args:
        input_path: Path to the uploaded original file.
        output_dir: Directory to save processed images.
        base_name: Base filename without extension (e.g. "abc123").
        sizes: List of size keys from _SIZES (default: ['full', 'thumb']).
        quality: JPEG quality (1-100).

    Returns:
        Dict mapping size key to relative URL path, e.g.:
        {'full': 'food/abc123_full.jpg', 'thumb': 'food/abc123_thumb.jpg'}
    """
    try:
        from PIL import Image, ExifTags
    except ImportError:
        logger.warning("Pillow not installed — skipping image processing")
        return {}

    if sizes is None:
        sizes = ['full', 'thumb']

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    results = {}

    try:
        img = Image.open(input_path)

        # Auto-rotate based on EXIF orientation (phone photos)
        try:
            for orientation in ExifTags.TAGS.keys():
                if ExifTags.TAGS[orientation] == 'Orientation':
                    break
            exif = img._getexif()
            if exif and orientation in exif:
                if exif[orientation] == 3:
                    img = img.rotate(180, expand=True)
                elif exif[orientation] == 6:
                    img = img.rotate(270, expand=True)
                elif exif[orientation] == 8:
                    img = img.rotate(90, expand=True)
        except (AttributeError, KeyError, TypeError):
            pass

        # Convert to RGB if needed (handles RGBA, palette, etc.)
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        for size_key in sizes:
            max_dims = _SIZES.get(size_key, _SIZES['full'])
            resized = img.copy()
            resized.thumbnail(max_dims, Image.LANCZOS)

            filename = f"{base_name}_{size_key}.jpg"
            out_path = Path(output_dir) / filename
            resized.save(str(out_path), 'JPEG', quality=quality, optimize=True)

            # Return path relative to uploads dir
            rel_dir = Path(output_dir).name
            results[size_key] = f"{rel_dir}/{filename}"

            file_size_kb = out_path.stat().st_size / 1024
            logger.info("Image %s: %dx%d, %.0fKB", size_key,
                        resized.width, resized.height, file_size_kb)

    except Exception as exc:
        logger.error("Image processing failed: %s", exc)

    return results


def process_upload(file_storage, upload_base_dir: str, subfolder: str,
                   base_name: str, sizes: list = None, quality: int = 80) -> dict:
    """Process a Flask FileStorage upload — save temp, process, clean up.

    Args:
        file_storage: Flask request.files[...] object.
        upload_base_dir: Base uploads directory (e.g. '/app/data/uploads').
        subfolder: Subdirectory (e.g. 'food', 'profiles').
        base_name: Filename base (e.g. UUID or user_id).
        sizes: Size variants to generate.
        quality: JPEG quality.

    Returns:
        Dict of size_key -> relative URL path.
    """
    import tempfile
    import os

    output_dir = Path(upload_base_dir) / subfolder
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save to temp file first
    ext = file_storage.filename.rsplit('.', 1)[-1].lower() if '.' in file_storage.filename else 'jpg'
    with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
        file_storage.save(tmp.name)
        tmp_path = tmp.name

    try:
        results = process_image(tmp_path, str(output_dir), base_name,
                                sizes=sizes, quality=quality)
    finally:
        os.unlink(tmp_path)

    return results
