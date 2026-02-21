import asyncio
import mimetypes
import random
import re
import secrets
import shlex
import string
from urllib.parse import urlparse

import psutil
from fastapi import UploadFile


def is_valid_name(name: str) -> bool:
    """
    Checks if a name contains only alphanumeric characters and spaces.

    Args:
        name: The name to validate (string).

    Returns:
        True if the name is valid, False otherwise.
    """
    pattern = r"^[a-zA-Z0-9\s()/\-.]+$"  # Alphanumeric and spaces and some special charaters only
    return bool(re.match(pattern, name))


def convert_name_to_id(name: str) -> str:
    """
    Converts a name into an ID by:
    1. Converting to lowercase.
    2. Replacing spaces with underscores.

    Args:
        name: The name to convert (string).

    Returns:
        The generated ID (string).  Returns None if the name is invalid.
    """

    # Remove leading/trailing spaces and multiple spaces inside.
    name = " ".join(name.split())
    return name.lower().replace(" ", "_")


def generate_short_password(length: int = 8) -> str:
    """
    Generates a random password with at least:
    - 8 characters
    - One uppercase letter
    - One lowercase letter
    - One number
    - One special character
    Args:
        length: Length of the password (minimum 8)
    Returns:
        A password string meeting the requirements.
    """
    upper = secrets.choice(string.ascii_uppercase)
    lower = secrets.choice(string.ascii_lowercase)
    digit = secrets.choice(string.digits)
    special = secrets.choice("!@#$%^&*()-_=+[]{};:,.<>?")
    others = [secrets.choice(string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{};:,.<>?") for _ in range(length - 4)]
    password_list = [upper, lower, digit, special, *others]
    random.shuffle(password_list)
    return "".join(password_list)


async def convert_office_doc(
    input_filename: str,
    output_directory: str,
    target_format: str = "docx",
    target_filter: str | None = None,
    wait_for_soffice_ready_time_out: int = 10,
) -> None:
    def validate_input(input_str: str) -> str:
        return shlex.quote(input_str)

    if target_filter is not None:
        target_format = f"{target_format}:{target_filter}"

    command = [
        "soffice",
        "--headless",
        "--convert-to",
        validate_input(target_format),
        "--outdir",
        validate_input(output_directory),
        validate_input(input_filename),
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        message = stdout.decode().strip()

        wait_time = 0
        sleep_time = 0.1
        while (wait_time < wait_for_soffice_ready_time_out) and (message == ""):
            wait_time += sleep_time
            if _is_soffice_running():
                await asyncio.sleep(sleep_time)
            else:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()
                message = stdout.decode().strip()

    except FileNotFoundError as e:
        msg = """
            soffice command was not found. Please install libreoffice
            on your system and try again.

            - Install instructions: https://www.libreoffice.org/get-help/install-howto/
            - Mac: https://formulae.brew.sh/cask/libreoffice
            - Debian: https://wiki.debian.org/LibreOffice
            """
        raise FileNotFoundError(
            msg,
        ) from e

    if process.returncode != 0 or message == "":
        msg = f"soffice failed to convert {input_filename} to {target_format}: {stderr.decode().strip()}"
        raise RuntimeError(
            msg,
        )


def _is_soffice_running() -> bool:
    for proc in psutil.process_iter():
        try:
            if "soffice" in proc.name().lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False


def validate_and_process(file: UploadFile) -> bool:
    mime_type, _ = mimetypes.guess_type(file.filename)
    return not (
        not mime_type
        or not mime_type.startswith(
            (
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/msword",
                "text/plain",
                "text/html",
                "text/csv",
                "application/vnd.ms-excel",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        )
    )


def is_valid_url(src: str) -> bool:
    try:
        result = urlparse(src)
        return all([result.scheme in ("http", "https"), result.netloc])
    except Exception:
        return False
