from pathlib import Path

import pytest

from tools import encoded_notes


def test_encrypt_decrypt_roundtrip() -> None:
    payload = encoded_notes.encrypt_note("secret note", "pass-123")
    plaintext = encoded_notes.decrypt_note(payload, "pass-123")
    assert plaintext == "secret note"


def test_decrypt_rejects_wrong_passphrase() -> None:
    payload = encoded_notes.encrypt_note("secret note", "correct")
    with pytest.raises(ValueError, match="invalid passphrase or corrupted note"):
        encoded_notes.decrypt_note(payload, "wrong")


def test_open_uses_pager_and_no_plaintext_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file_path = tmp_path / "note.enc"
    payload = encoded_notes.encrypt_note("one\ntwo\nthree\n", "pw")
    file_path.write_text(payload, encoding="utf-8")

    captured = {"text": None}

    def fake_pager(text: str) -> None:
        captured["text"] = text

    monkeypatch.setattr(encoded_notes.pydoc, "pager", fake_pager)
    args = encoded_notes.build_parser().parse_args(["open", "-f", str(file_path), "-p", "pw"])
    exit_code = encoded_notes.cmd_open(args)

    assert exit_code == 0
    assert captured["text"] == "one\ntwo\nthree\n"
    assert list(tmp_path.iterdir()) == [file_path]

