"""Tests for multimodal prompt types."""

import base64

from cody.core.prompt import (
    ImageData,
    MultimodalPrompt,
    prompt_images,
    prompt_text,
)


# ── ImageData ────────────────────────────────────────────────────────────────


def test_image_data_roundtrip():
    raw = b"\x89PNG\r\n\x1a\n"
    b64 = base64.b64encode(raw).decode()
    img = ImageData(data=b64, media_type="image/png", filename="test.png")
    assert img.data_bytes == raw
    d = img.to_dict()
    restored = ImageData.from_dict(d)
    assert restored.data == b64
    assert restored.media_type == "image/png"
    assert restored.filename == "test.png"


def test_image_data_no_filename():
    img = ImageData(data="aGVsbG8=", media_type="image/jpeg")
    d = img.to_dict()
    assert "filename" not in d
    restored = ImageData.from_dict(d)
    assert restored.filename is None


def test_image_data_data_bytes():
    raw = b"hello"
    b64 = base64.b64encode(raw).decode()
    img = ImageData(data=b64, media_type="image/png")
    assert img.data_bytes == raw


# ── prompt_text ──────────────────────────────────────────────────────────────


def test_prompt_text_from_str():
    assert prompt_text("hello") == "hello"


def test_prompt_text_from_multimodal():
    p = MultimodalPrompt(text="analyze this", images=[])
    assert prompt_text(p) == "analyze this"


# ── prompt_images ────────────────────────────────────────────────────────────


def test_prompt_images_from_str():
    assert prompt_images("hello") == []


def test_prompt_images_from_multimodal():
    img = ImageData(data="aGVsbG8=", media_type="image/png")
    p = MultimodalPrompt(text="look at this", images=[img])
    result = prompt_images(p)
    assert len(result) == 1
    assert result[0].media_type == "image/png"


def test_prompt_images_empty_multimodal():
    p = MultimodalPrompt(text="no images")
    assert prompt_images(p) == []


# ── MultimodalPrompt ────────────────────────────────────────────────────────


def test_multimodal_prompt_defaults():
    p = MultimodalPrompt(text="hello")
    assert p.text == "hello"
    assert p.images == []


def test_multimodal_prompt_with_images():
    img1 = ImageData(data="aGVsbG8=", media_type="image/png", filename="a.png")
    img2 = ImageData(data="d29ybGQ=", media_type="image/jpeg")
    p = MultimodalPrompt(text="compare", images=[img1, img2])
    assert len(p.images) == 2
    assert p.images[0].filename == "a.png"
    assert p.images[1].filename is None
