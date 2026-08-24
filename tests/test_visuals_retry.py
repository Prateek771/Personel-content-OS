import re
import time
from pathlib import Path

import pytest

from intelligence_os.content.linkedin import LinkedInCarouselSlide
from intelligence_os.visuals.openrouter_image import OpenRouterImageGenerator


def _slides(n=5):
    return [
        LinkedInCarouselSlide(
            slide_number=i, title=f"T{i}", subtitle=f"B{i}", bullet_points=[], takeaway=""
        )
        for i in range(1, n + 1)
    ]


def _make_gen(monkeypatch, behavior, tmp_path):
    """behavior(idx) -> bool controlling per-slide Grok success (one call per slide)."""
    gen = OpenRouterImageGenerator.__new__(OpenRouterImageGenerator)
    gen.api_key = "test-key"
    gen.base_url = "https://example"
    gen.image_model = "m"
    gen.output_dir = tmp_path / "generated_images"

    def fake_generate(prompt, path):
        m = re.search(r"SLIDE: (\d+)", prompt)
        idx = int(m.group(1)) - 1 if m else 0
        ok = behavior(idx)
        if ok:
            path.write_bytes(b"\x89PNG\r\n\x1a\n")
            return True
        return False

    gen._generate_to_file = fake_generate
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)
    return gen


def test_all_five_built_on_success(monkeypatch, tmp_path):
    gen = _make_gen(monkeypatch, lambda i: True, tmp_path)
    paths = gen.generate_carousel_images(_slides(5), "ART", "draft-x")
    assert len(paths) == 5
    assert all(Path(p).exists() for p in paths)


def test_one_slide_falls_back_to_pillow_still_five(monkeypatch, tmp_path):
    # Slide 3 (idx 2) fails Grok; the per-slide Pillow fallback should still yield 5.
    gen = _make_gen(monkeypatch, lambda i: i != 2, tmp_path)
    paths = gen.generate_carousel_images(_slides(5), "ART", "draft-y")
    assert len(paths) == 5
    assert all(Path(p).exists() for p in paths)


def test_all_fail_grok_still_yields_five_via_pillow(monkeypatch, tmp_path):
    gen = _make_gen(monkeypatch, lambda i: False, tmp_path)
    paths = gen.generate_carousel_images(_slides(5), "ART", "draft-z")
    # Channel still returns a complete 5-slide set even when the image model is down.
    assert len(paths) == 5
    assert all(Path(p).exists() for p in paths)
