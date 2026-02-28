#!/usr/bin/env python3
"""Small local encrypted notes utility.

Usage:
  python tools/encoded_notes.py write -f .notes.enc
  python tools/encoded_notes.py read -f .notes.enc
  python tools/encoded_notes.py open -f .notes.enc
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import pydoc
import secrets
import sys
from pathlib import Path

VERSION = 1
SALT_BYTES = 16
NONCE_BYTES = 16
KDF_ITERATIONS = 200_000


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _b64d(encoded: str) -> bytes:
    return base64.urlsafe_b64decode(encoded.encode("ascii"))


def _derive_keys(passphrase: str, salt: bytes, iterations: int) -> tuple[bytes, bytes]:
    key_material = hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        salt,
        iterations,
        dklen=64,
    )
    return key_material[:32], key_material[32:]


def _xor_stream(enc_key: bytes, nonce: bytes, data: bytes) -> bytes:
    out = bytearray(len(data))
    counter = 0
    offset = 0
    while offset < len(data):
        ctr = counter.to_bytes(8, byteorder="big", signed=False)
        block = hmac.new(enc_key, nonce + ctr, hashlib.sha256).digest()
        chunk = min(len(block), len(data) - offset)
        for i in range(chunk):
            out[offset + i] = data[offset + i] ^ block[i]
        offset += chunk
        counter += 1
    return bytes(out)


def encrypt_note(plaintext: str, passphrase: str, iterations: int = KDF_ITERATIONS) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    nonce = secrets.token_bytes(NONCE_BYTES)
    enc_key, mac_key = _derive_keys(passphrase, salt, iterations)
    plaintext_bytes = plaintext.encode("utf-8")
    ciphertext = _xor_stream(enc_key, nonce, plaintext_bytes)
    tag = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    payload = {
        "version": VERSION,
        "kdf": "pbkdf2-sha256",
        "iterations": iterations,
        "salt": _b64e(salt),
        "nonce": _b64e(nonce),
        "ciphertext": _b64e(ciphertext),
        "tag": _b64e(tag),
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def decrypt_note(payload_text: str, passphrase: str) -> str:
    try:
        payload = json.loads(payload_text)
        if payload.get("version") != VERSION:
            raise ValueError("unsupported note version")

        salt = _b64d(payload["salt"])
        nonce = _b64d(payload["nonce"])
        ciphertext = _b64d(payload["ciphertext"])
        expected_tag = _b64d(payload["tag"])
        iterations = int(payload["iterations"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid encoded note format") from exc

    enc_key, mac_key = _derive_keys(passphrase, salt, iterations)
    computed_tag = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_tag, computed_tag):
        raise ValueError("invalid passphrase or corrupted note")

    plaintext_bytes = _xor_stream(enc_key, nonce, ciphertext)
    return plaintext_bytes.decode("utf-8")


def _read_passphrase(provided: str | None) -> str:
    if provided:
        return provided

    env_passphrase = os.environ.get("NOTE_PASSPHRASE")
    if env_passphrase:
        return env_passphrase

    if not sys.stdin.isatty():
        raise ValueError("passphrase required in non-interactive mode")
    return getpass.getpass("Passphrase: ")


def _write_secure(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(path, 0o600)


def _load_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def cmd_write(args: argparse.Namespace) -> int:
    passphrase = _read_passphrase(args.passphrase)

    if args.note is not None:
        note = args.note
    else:
        note = sys.stdin.read()
        if not note and sys.stdin.isatty():
            raise ValueError("provide --note or pipe note content via stdin")

    encoded = encrypt_note(note, passphrase, iterations=args.iterations)
    _write_secure(args.file, encoded)
    print(f"Saved encoded note to {args.file}")
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    passphrase = _read_passphrase(args.passphrase)
    payload = _load_file(args.file)
    plaintext = decrypt_note(payload, passphrase)
    print(plaintext, end="")
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    passphrase = _read_passphrase(args.passphrase)
    payload = _load_file(args.file)
    plaintext = decrypt_note(payload, passphrase)
    pydoc.pager(plaintext)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local encrypted notes tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_flags(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "-f",
            "--file",
            type=Path,
            default=Path(".notes.enc"),
            help="Path to encoded note file (default: .notes.enc)",
        )
        sp.add_argument(
            "-p",
            "--passphrase",
            default=None,
            help="Passphrase (unsafe in shell history; prefer NOTE_PASSPHRASE env or prompt)",
        )

    write_parser = subparsers.add_parser("write", help="Encrypt and save a note")
    add_common_flags(write_parser)
    write_parser.add_argument("-n", "--note", default=None, help="Note text; if omitted, read stdin")
    write_parser.add_argument(
        "--iterations",
        type=int,
        default=KDF_ITERATIONS,
        help=f"KDF iterations (default: {KDF_ITERATIONS})",
    )
    write_parser.set_defaults(func=cmd_write)

    read_parser = subparsers.add_parser("read", help="Decrypt and print a note")
    add_common_flags(read_parser)
    read_parser.set_defaults(func=cmd_read)

    open_parser = subparsers.add_parser("open", help="Decrypt and open note in pager")
    add_common_flags(open_parser)
    open_parser.set_defaults(func=cmd_open)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

