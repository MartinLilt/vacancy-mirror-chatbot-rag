import tempfile
import unittest
from pathlib import Path

from baltic_marketplace.images import service as image_service
from baltic_marketplace.images.service import (
    ImageConfig,
    ImageGenerator,
    _build_image_prompt,
    _build_multipart_body,
    _finalize_generation_prompt,
    _normalize_reference_analysis,
    _select_image_size,
    cache_reference_images,
)


class ImageServiceTests(unittest.TestCase):
    def test_build_image_prompt_uses_draft_fields(self):
        prompt = _build_image_prompt(
            draft={
                "post_title": "Title",
                "hook": "Hook",
                "body_sections": ["A", "B"],
                "asset_suggestion": "Use a simple visual",
            }
        )

        self.assertIn("Title", prompt)
        self.assertIn("Hook", prompt)
        self.assertIn("Use a simple visual", prompt)

    def test_build_multipart_body_includes_fields_and_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "ref.jpg"
            file_path.write_bytes(b"abc")
            body = _build_multipart_body(
                boundary="test-boundary",
                fields=[("model", "gpt-image-1.5")],
                files=[("image[]", file_path)],
            )

        self.assertIn(b'name="model"', body)
        self.assertIn(b"gpt-image-1.5", body)
        self.assertIn(b'filename="ref.jpg"', body)
        self.assertIn(b"abc", body)

    def test_cache_reference_images_saves_downloaded_files(self):
        original_downloader = image_service._download_public_file

        def fake_downloader(url, target):
            target.write_bytes(b"img")

        image_service._download_public_file = fake_downloader
        try:
            with tempfile.TemporaryDirectory() as tmp:
                result = cache_reference_images(
                    posts_dataset={
                        "posts": [
                            {"image_url": "https://example.com/1.jpg"},
                            {"image_url": "https://example.com/2.jpg"},
                        ]
                    },
                    refs_dir=tmp,
                    limit=1,
                )
                self.assertEqual(result["cached_count"], 1)
                self.assertEqual(len(result["cached_files"]), 1)
                self.assertTrue(Path(result["cached_files"][0]).exists())
        finally:
            image_service._download_public_file = original_downloader

    def test_create_post_image_includes_reference_analysis_and_visual_brief(self):
        generator = ImageGenerator(ImageConfig("key", "gpt-image-1.5", "gpt-4.1-mini", 10))
        with tempfile.TemporaryDirectory() as tmp:
            refs_dir = Path(tmp) / "refs"
            refs_dir.mkdir()
            (refs_dir / "reference_1.jpg").write_bytes(b"img")
            out_path = Path(tmp) / "image.png"
            metadata_path = Path(tmp) / "meta.json"

            generator._analyze_reference_images = lambda **kwargs: {  # type: ignore[attr-defined]
                "style_summary": "Minimal visual",
                "composition_type": "single focal point",
                "locked_palette": ["deep purple"],
                "locked_shapes": ["rounded panels"],
                "locked_style_rules": ["minimal text"],
                "optional_concept_patterns": ["split-screen"],
            }
            generator._build_visual_brief = lambda **kwargs: {  # type: ignore[attr-defined]
                "best_visual_metaphor_for_this_post": "single hero chart block",
                "core_visual_idea": "One chart block",
                "do_not_change": ["dark cosmic mood"],
                "generation_prompt": "Minimal SaaS image",
            }
            generator._generate_image_with_references = lambda **kwargs: b"png"  # type: ignore[attr-defined]

            metadata = generator.create_post_image(
                draft_payload={"draft": {"post_title": "Title", "hook": "Hook"}},
                posts_dataset={"posts": [{"image_url": "https://example.com/1.jpg"}]},
                refs_dir=refs_dir,
                output_path=out_path,
                metadata_path=metadata_path,
                reference_limit=1,
            )

            self.assertEqual(metadata["reference_analysis"]["style_summary"], "Minimal visual")
            self.assertEqual(metadata["visual_brief"]["core_visual_idea"], "One chart block")
            self.assertIn("Minimal SaaS image", metadata["prompt"])
            self.assertTrue(out_path.exists())

    def test_select_image_size_prefers_landscape_when_refs_are_landscape(self):
        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x05\x00"
            b"\x00\x00\x03\x55"
            b"\x08\x02\x00\x00\x00"
            b"\x00\x00\x00\x00"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reference_1.png"
            path.write_bytes(png_bytes)
            self.assertEqual(_select_image_size([path]), "1536x1024")

    def test_finalize_generation_prompt_includes_locked_style_constraints(self):
        prompt = _finalize_generation_prompt(
            generation_prompt="Base prompt.",
            reference_analysis={
                "locked_palette": ["deep purple", "electric blue"],
                "locked_shapes": ["rounded panels"],
                "locked_style_rules": ["minimal text", "high contrast"],
                "optional_concept_patterns": ["single hero comparison"],
            },
            visual_brief={
                "best_visual_metaphor_for_this_post": "single glowing plugin block",
                "do_not_change": ["dark cosmic mood"],
                "headline_text": "ONE PLUGIN",
                "bottom_caption_text": "Less friction inside the tool",
            },
        )
        self.assertIn("deep purple", prompt)
        self.assertIn("rounded panels", prompt)
        self.assertIn("dark cosmic mood", prompt)
        self.assertIn("single glowing plugin block", prompt)
        self.assertIn("3 to 6 words maximum", prompt)
        self.assertIn("Less friction inside the tool", prompt)

    def test_normalize_reference_analysis_demotes_split_and_flow_bias(self):
        normalized = _normalize_reference_analysis(
            {
                "locked_style_rules": [
                    "Use cosmic background",
                    "Consistent dual panel or flow diagram layouts for contrast",
                ],
                "visual_rules": [
                    "Use arrows and flow connectors for process storytelling",
                    "Keep background subtle",
                ],
                "optional_concept_patterns": ["robot mascot"],
                "avoid": [],
            }
        )

        self.assertIn("Use cosmic background", normalized["locked_style_rules"])
        self.assertNotIn(
            "Consistent dual panel or flow diagram layouts for contrast",
            normalized["locked_style_rules"],
        )
        self.assertNotIn(
            "Use arrows and flow connectors for process storytelling",
            normalized["visual_rules"],
        )
        self.assertIn("split-screen default layout", normalized["avoid"])


if __name__ == "__main__":
    unittest.main()
