import base64
import time
from collections.abc import Callable, Generator, Iterator
from functools import wraps
from pathlib import Path
from typing import TypeVar, cast

from Cryptodome.Cipher import AES
from Cryptodome.Hash import SHA256
from Cryptodome.Util.Padding import pad, unpad
from langchain_core.tools import StructuredTool

from initializer import logger_instance, settings
from schemas.knowledge_base import QueryKBInput

F = TypeVar("F", bound=Callable)
FG = TypeVar("FG", bound=Callable[..., Generator | Iterator])
logger = logger_instance.get_logger(__name__)


def log_function_time(
    func_name: str | None = None,
    debug_only: bool = True,
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapped_func(*args: any, **kwargs: any) -> any:
            start_time = time.time()
            result = await func(*args, **kwargs)
            elapsed_time_str = str(time.time() - start_time)
            log_name = func_name or func.__name__
            final_log = f'event=show-func-execute-time function={log_name} message="Elapsed time: {elapsed_time_str} seconds."'
            if debug_only:
                logger.debug(final_log)
            else:
                logger.info(final_log)

            return result

        return cast(F, wrapped_func)

    return decorator


def get_aes_key_from_secret(secret: str) -> bytes:
    """
    Derives a 256-bit AES key from a secret string using SHA-256.
    This must produce the exact same key as the JS `getAesKeyFromSecret` function.
    """
    hasher = SHA256.new(secret.encode("utf-8"))
    return hasher.digest()


def encrypt_secure(plain_str: str) -> str:
    """
    Encrypts a string securely using AES in CBC mode with a random IV.

    The IV is prepended to the ciphertext, and the result is Base64 encoded.

    :param plain_str: The string to encrypt.
    :return: The Base64 encoded string containing (IV + ciphertext).
    """
    try:
        key = get_aes_key_from_secret(settings.ENCRYPTION_KEY.get_secret_value())
        data_to_encrypt = plain_str.encode("utf-8")
        cipher = AES.new(key, AES.MODE_CBC)
        iv = cipher.iv
        padded_data = pad(data_to_encrypt, AES.block_size)
        encrypted_bytes = cipher.encrypt(padded_data)
        payload = iv + encrypted_bytes
        encoded_payload = base64.b64encode(payload)

        return encoded_payload.decode("utf-8")
    except Exception:
        logger.exception('event=encrypt-key-secure message="An error occurred during secure encryption"')
        return ""


def decrypt_secure(encrypted_str: str) -> str:
    """
    Decrypts a string that was securely encrypted with its IV prepended.

    :param encrypted_str: The Base64 encoded string (IV + ciphertext).
    :return: The original, decrypted string.
    """
    try:
        data = base64.b64decode(encrypted_str)
        iv = data[: AES.block_size]
        ciphertext = data[AES.block_size :]
        key = get_aes_key_from_secret(settings.ENCRYPTION_KEY.get_secret_value())
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted_bytes = unpad(cipher.decrypt(ciphertext), AES.block_size)
        return decrypted_bytes.decode("utf-8")
    except (ValueError, KeyError, IndexError):
        logger.exception(
            'event=decrypt-key-securemessage="Decryption failed. Data may be corrupt or in old format."',
        )
        return ""


def decrypt_static_iv(encrypted_str: str) -> str:
    # This is your original decrypt function
    try:
        ciphertext = base64.b64decode(encrypted_str)
        iv = bytes.fromhex("00000000000000000000000000000000")
        key = get_aes_key_from_secret(settings.ENCRYPTION_KEY.get_secret_value())
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
        return decrypted.decode("utf-8")
    except Exception:
        return ""  # Return empty on failure


def decrypt_and_migrate(encrypted_str: str) -> str:
    """
    Tries to decrypt using the new secure method first,
    then falls back to the old static IV method.
    """
    # 1. Try the new, secure method first.
    if not encrypted_str:
        return ""

    decrypted_value = decrypt_secure(encrypted_str)

    # 2. If it fails, it will return an empty string. Then try the old method.
    if not decrypted_value:
        decrypted_value = decrypt_static_iv(encrypted_str)
    return decrypted_value


def make_kb_tool(kb: dict[str, str], query_func: any) -> any:
    async def wrapped(query: str) -> str:
        return await query_func(kb_name=kb["name"], query=query)

    return StructuredTool.from_function(
        coroutine=wrapped,
        name=f"query_{kb['name']}_kb",
        description=kb["description"],
        args_schema=QueryKBInput,
    )


def list_files_pathlib(directory_path: str) -> list[str]:
    """Lists all files in the specified directory using the pathlib module."""
    path = Path(directory_path)
    return [entry.name for entry in path.iterdir() if entry.is_file()]
