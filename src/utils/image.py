import asyncio
import base64
import zipfile
from io import BytesIO
from pathlib import Path

import aiofiles
import aiofiles.tempfile
from fastapi import UploadFile
from PIL import Image

from utils.constants import IMAGE_MODE, INVALID_FILE_TYPE_MSG
from utils.enums import ImageFileExtension, ImageFormat


def convert_pil_to_base64(image: Image.Image, img_format: str | None = None, quality: int = 95) -> str:
    """Convert a PIL Image to base64 string with high quality settings.

    Args:
        image (Image): PIL Image object
        img_format (str, optional): Image format to save as. If None, uses PNG for better quality
        quality (int): JPEG quality setting (95 for high quality, ignored for PNG)

    Returns:
        str: Base64 encoded string of the image
    """
    if not img_format:
        # Default to PNG for better quality (lossless compression)
        img_format = ImageFormat.PNG if image.mode in ("RGBA", "LA") else ImageFormat.JPEG
    else:
        try:
            img_format = ImageFormat(img_format.upper())
        except ValueError:
            img_format = ImageFormat.PNG  # Default to PNG for better quality

    buffer = BytesIO()

    # Handle RGBA to JPEG conversion if necessary
    if img_format == ImageFormat.JPEG and image.mode == IMAGE_MODE:
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])
        image = background

    # Save with high quality settings
    if img_format == ImageFormat.JPEG:
        image.save(buffer, format=img_format, quality=quality, optimize=True)
    else:
        # PNG is lossless, no quality parameter needed
        image.save(buffer, format=img_format, optimize=True)

    image_bytes = buffer.getvalue()
    base64_encoded = base64.b64encode(image_bytes)
    return base64_encoded.decode("utf-8")


async def extract_images_from_zip(zip_file: UploadFile) -> list[Image.Image] | None:
    """Extract and load images from zip file.

    Args:
        zip_file: ZIP file containing images

    Returns:
        List of PIL Image objects or None if error occurs
    """
    try:
        async with aiofiles.tempfile.TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / zip_file.filename
            async with aiofiles.open(zip_path, "wb") as f:
                content = await zip_file.read()
                await f.write(content)

            # Use asyncio.to_thread for CPU-bound operations
            def extract_zip(zip_path: Path, temp_dir: str) -> None:
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(temp_dir)

            await asyncio.to_thread(extract_zip, zip_path, temp_dir)

            temp_dir_path = Path(temp_dir)
            folder_name = next(f.name for f in temp_dir_path.iterdir() if f.is_dir())

            temp_dir_images_path = Path(temp_dir) / folder_name
            image_files = list(
                reversed(
                    [f for f in temp_dir_images_path.iterdir() if f.name.lower().endswith(tuple(ImageFileExtension.to_list()))],
                ),
            )

            # Use asyncio.to_thread for CPU-bound image loading
            def load_images(image_paths: list[Path]) -> list[Image.Image]:
                return [Image.open(img_path).copy() for img_path in image_paths]

            return await asyncio.to_thread(load_images, image_files)

    except Exception:
        return None


async def validate_zip_file(
    zip_file: UploadFile,
) -> tuple[bool, str | list[Image.Image]]:
    if not zip_file.filename.lower().endswith(".zip"):
        raise ValueError(INVALID_FILE_TYPE_MSG)

    images = await extract_images_from_zip(zip_file)
    if images is None:
        return False, "Extract images from zip file failed"

    return True, images
