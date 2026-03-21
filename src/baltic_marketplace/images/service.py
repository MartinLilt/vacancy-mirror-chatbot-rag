"""OpenAI image generation service with reference images."""

from __future__ import annotations

import json
import mimetypes
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

from baltic_marketplace.openai_api.service import OpenAIService


DEFAULT_IMAGE_MODEL = "gpt-image-1.5"
DEFAULT_IMAGE_ANALYSIS_MODEL = "gpt-4.1-mini"
DEFAULT_IMAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Referer": "https://www.linkedin.com/",
}


class ImageGenerationError(RuntimeError):
    """Raised when image generation cannot be completed."""


@dataclass(frozen=True)
class ImageConfig:
    api_key: str
    model: str
    analysis_model: str
    timeout_seconds: int = 180

    @classmethod
    def from_env(cls, *, default_model: str | None = None) -> "ImageConfig":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ImageGenerationError("Переменная окружения OPENAI_API_KEY не задана.")

        model = default_model or os.getenv("OPENAI_IMAGE_MODEL", "").strip() or DEFAULT_IMAGE_MODEL
        analysis_model = (
            os.getenv("OPENAI_IMAGE_ANALYSIS_MODEL", "").strip() or DEFAULT_IMAGE_ANALYSIS_MODEL
        )
        timeout_raw = os.getenv("OPENAI_IMAGE_TIMEOUT_SECONDS", "180").strip() or "180"

        try:
            timeout_seconds = int(timeout_raw)
        except ValueError as exc:
            raise ImageGenerationError(
                "OPENAI_IMAGE_TIMEOUT_SECONDS должен быть целым числом."
            ) from exc

        return cls(
            api_key=api_key,
            model=model,
            analysis_model=analysis_model,
            timeout_seconds=timeout_seconds,
        )


class ImageGenerator:
    """Generates a LinkedIn image using past-post image references."""

    def __init__(self, config: ImageConfig) -> None:
        self._config = config

    @classmethod
    def from_env(cls, *, default_model: str | None = None) -> "ImageGenerator":
        return cls(ImageConfig.from_env(default_model=default_model))

    def create_post_image(
        self,
        *,
        draft_payload: dict[str, Any],
        posts_dataset: dict[str, Any],
        refs_dir: str | Path,
        output_path: str | Path,
        metadata_path: str | Path,
        reference_limit: int = 3,
    ) -> dict[str, Any]:
        draft = draft_payload.get("draft")
        posts = posts_dataset.get("posts")
        if not isinstance(draft, dict):
            raise ImageGenerationError("draft_payload must contain a 'draft' object.")
        if not isinstance(posts, list) or not posts:
            raise ImageGenerationError("posts_dataset must contain a non-empty 'posts' list.")

        refs_dir = Path(refs_dir)
        refs_dir.mkdir(parents=True, exist_ok=True)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path = Path(metadata_path)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)

        reference_files = self._resolve_reference_images(
            posts=posts,
            refs_dir=refs_dir,
            limit=reference_limit,
        )
        image_size = _select_image_size(reference_files)
        reference_analysis = self._analyze_reference_images(
            draft=draft,
            reference_files=reference_files,
        )
        reference_analysis = _normalize_reference_analysis(reference_analysis)
        visual_brief = self._build_visual_brief(
            draft=draft,
            reference_analysis=reference_analysis,
        )
        prompt = _finalize_generation_prompt(
            generation_prompt=visual_brief["generation_prompt"],
            reference_analysis=reference_analysis,
            visual_brief=visual_brief,
        )
        warnings: list[str] = []
        if reference_files:
            image_bytes = self._generate_image_with_references(
                prompt=prompt,
                reference_files=reference_files,
                size=image_size,
            )
        else:
            warnings.append(
                "Reference images were unavailable from LinkedIn CDN, so the image was generated without visual references."
            )
            image_bytes = self._generate_image_without_references(
                prompt=prompt,
                size=image_size,
            )
        output_path.write_bytes(image_bytes)

        metadata = {
            "model": self._config.model,
            "size": image_size,
            "prompt": prompt,
            "reference_images": [str(path) for path in reference_files],
            "reference_analysis": reference_analysis,
            "visual_brief": visual_brief,
            "output_image": str(output_path),
            "warnings": warnings,
        }
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return metadata

    def _text_llm(self) -> OpenAIService:
        return OpenAIService.from_env(default_model=self._config.analysis_model)

    def _analyze_reference_images(
        self,
        *,
        draft: dict[str, Any],
        reference_files: list[Path],
    ) -> dict[str, Any]:
        if not reference_files:
            return {
                "style_summary": "No visual references available. Use a clean, minimal, SaaS visual direction.",
                "composition_type": "single focal point cover",
                "text_density": "none to minimal",
                "visual_rules": [
                    "Keep one strong visual idea",
                    "Prefer a single-scene cover image over an explainer layout",
                    "Use large simple headline hierarchy",
                    "Avoid tiny visual details that disappear at thumbnail size",
                    "Avoid infographic density",
                    "Avoid too much UI clutter",
                ],
                "avoid": [
                    "busy dashboards",
                    "multi-panel layouts",
                    "triptych layouts",
                    "heavy text overlays",
                    "step-by-step panels",
                    "flowchart/process diagrams",
                    "default robot mascot usage",
                    "arrow-driven compositions",
                ],
            }

        system_prompt = (
            "You are a visual art-direction analyst for LinkedIn product posts. "
            "Analyze the reference images and return JSON only. "
            "Focus on style, composition, density, color mood, text usage, focal point, and recurring visual rules. "
            "Do not describe every detail. Separate what must remain visually consistent from what is only an optional concept pattern. "
            "Treat semantic motifs such as robots, humans, before/after stories, headings, labels, diagrams, arrows, and UI walkthroughs as optional concept patterns unless they are truly unavoidable style primitives. "
            "Prefer extracting deep style primitives: palette, texture, glow logic, shape language, scene density, and visual polish. "
            "Do not lock specific mascot characters, human portraits, or before/after storytelling as required style unless every reference depends on them. "
            "JSON schema: "
            "{"
            "\"style_summary\":string,"
            "\"composition_type\":string,"
            "\"color_mood\":string,"
            "\"text_density\":string,"
            "\"focal_point_style\":string,"
            "\"locked_palette\":[string],"
            "\"locked_shapes\":[string],"
            "\"locked_style_rules\":[string],"
            "\"optional_concept_patterns\":[string],"
            "\"visual_rules\":[string],"
            "\"avoid\":[string]"
            "}"
        )
        user_prompt = (
            "Analyze these cached LinkedIn post images as style references for a new post cover. "
            f"Draft title context: {draft.get('post_title') or ''}. "
            f"Draft hook context: {draft.get('hook') or ''}."
        )
        return self._text_llm().generate_json_from_image_paths(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            image_paths=reference_files,
        )

    def _build_visual_brief(
        self,
        *,
        draft: dict[str, Any],
        reference_analysis: dict[str, Any],
    ) -> dict[str, Any]:
        system_prompt = (
            "You are a visual brief generator for LinkedIn post covers. "
            "Take the draft message and the reference style analysis, then compress them into one strong visual concept. "
            "Return JSON only. "
            "The result must be minimal, focused, and suitable for a single-image LinkedIn post cover. "
            "Default to a single-scene cover image with one dominant focal idea. "
            "Prefer a short in-image title similar to LinkedIn cover-style graphics when the references support it. "
            "Use a large top-centered title with 3 to 6 words maximum. "
            "Allow an optional smaller supporting subtitle or bottom caption, but both must stay short and highly legible. "
            "If the concept works as a comparison, use one large top title plus two smaller side labels or framed mini-labels that explain the contrast. "
            "You may also use one bottom-center caption with 6 to 9 words maximum to clarify what is happening. "
            "Always think at LinkedIn thumbnail scale: avoid tiny details, tiny labels, dense UI, or anything that becomes unreadable when small. "
            "Prefer two main silhouettes or two strong visual masses over one lone object when possible, because paired contrast reads better in this style. "
            "Do not use triptych, three-panel, storyboard, or multi-stage comparison layouts. "
            "Do not propose carousel logic, step panels, process diagrams, flowcharts, code snippets, charts with readable labels, JSON schemas, overloaded UI, or any major stylistic deviation from the reference images unless the current post absolutely requires it. "
            "Do not use a robot, mascot, human figure, or character unless it is truly essential to the best visual metaphor for the current post. "
            "Do not use arrows or connectors as the main compositional logic unless absolutely unavoidable. "
            "Prefer a cover-style symbolic scene over an explanatory scene. "
            "Prefer abstracted product cues, interface fragments, light, form, motion, and one clean focal object instead of storytelling characters. "
            "A single plugin window, single symbolic module, or single luminous product object is preferred over multiple boxes or process sequences. "
            "Do not use strong outcome claims in the image headline unless they are confirmed facts; prefer idea-driven or directional wording. "
            "You must preserve the reference visual language as much as possible, especially palette, texture, shape language, and concept simplicity. "
            "Do not copy a recurring composition pattern from the references unless it is clearly the best metaphor for the current post. "
            "Choose the best visual metaphor for this specific post first, then express it in the reference style. "
            "JSON schema: "
            "{"
            "\"best_visual_metaphor_for_this_post\":string,"
            "\"core_visual_idea\":string,"
            "\"composition\":string,"
            "\"background\":string,"
            "\"focal_element\":string,"
            "\"text_treatment\":string,"
            "\"headline_text\":string,"
            "\"subheadline_text\":string,"
            "\"left_label_text\":string,"
            "\"right_label_text\":string,"
            "\"bottom_caption_text\":string,"
            "\"style_constraints\":[string],"
            "\"do_not_change\":[string],"
            "\"generation_prompt\":string"
            "}"
        )
        user_prompt = json.dumps(
            {
                "draft": {
                    "post_title": draft.get("post_title"),
                    "hook": draft.get("hook"),
                    "body_sections": draft.get("body_sections"),
                    "asset_suggestion": draft.get("asset_suggestion"),
                    "image_headline": draft.get("image_headline"),
                    "image_subheadline": draft.get("image_subheadline"),
                },
                "reference_analysis": reference_analysis,
            },
            ensure_ascii=False,
            indent=2,
        )
        return self._text_llm().generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    def _resolve_reference_images(
        self,
        *,
        posts: list[dict[str, Any]],
        refs_dir: Path,
        limit: int,
    ) -> list[Path]:
        cached_files = self._cached_reference_images(refs_dir=refs_dir, limit=limit)
        if cached_files:
            return cached_files

        return self._download_reference_images(posts=posts, refs_dir=refs_dir, limit=limit)

    def _cached_reference_images(self, *, refs_dir: Path, limit: int) -> list[Path]:
        cached = sorted(refs_dir.glob("reference_*.jpg"))
        return cached[:limit]

    def _download_reference_images(
        self,
        *,
        posts: list[dict[str, Any]],
        refs_dir: Path,
        limit: int,
    ) -> list[Path]:
        results: list[Path] = []
        for index, post in enumerate(posts, start=1):
            image_url = post.get("image_url")
            if not isinstance(image_url, str) or not image_url.strip():
                continue
            target = refs_dir / f"reference_{index}.jpg"
            try:
                self._download_file(image_url, target)
            except ImageGenerationError:
                continue
            results.append(target)
            if len(results) >= limit:
                break
        return results

    def _download_file(self, url: str, target: Path) -> None:
        req = request.Request(url, headers=DEFAULT_IMAGE_HEADERS, method="GET")
        try:
            with request.urlopen(req, timeout=self._config.timeout_seconds) as response:
                target.write_bytes(response.read())
        except error.HTTPError as exc:
            raise ImageGenerationError(
                f"Не удалось скачать reference image: {exc.code} {url}"
            ) from exc
        except error.URLError as exc:
            raise ImageGenerationError(
                f"Не удалось подключиться для скачивания reference image: {exc.reason}"
            ) from exc

    def _generate_image_with_references(
        self,
        *,
        prompt: str,
        reference_files: list[Path],
        size: str,
    ) -> bytes:
        boundary = f"----CodexBoundary{uuid.uuid4().hex}"
        body = _build_multipart_body(
            boundary=boundary,
            fields=[
                ("model", self._config.model),
                ("prompt", prompt),
                ("size", size),
                ("quality", "medium"),
            ],
            files=[("image[]", path) for path in reference_files],
        )

        req = request.Request(
            "https://api.openai.com/v1/images/edits",
            data=body,
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self._config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ImageGenerationError(
                f"OpenAI Image API вернул {exc.code}: {body}"
            ) from exc
        except error.URLError as exc:
            raise ImageGenerationError(
                f"Не удалось подключиться к OpenAI Image API: {exc.reason}"
            ) from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ImageGenerationError("OpenAI Image API вернул невалидный JSON.") from exc

        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise ImageGenerationError("OpenAI Image API не вернул image data.")

        b64_json = data[0].get("b64_json")
        if not isinstance(b64_json, str) or not b64_json.strip():
            raise ImageGenerationError("OpenAI Image API не вернул b64_json.")

        import base64

        return base64.b64decode(b64_json)

    def _generate_image_without_references(self, *, prompt: str, size: str) -> bytes:
        body = {
            "model": self._config.model,
            "prompt": prompt,
            "size": size,
            "quality": "medium",
        }

        req = request.Request(
            "https://api.openai.com/v1/images/generations",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self._config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ImageGenerationError(
                f"OpenAI Image API вернул {exc.code}: {body}"
            ) from exc
        except error.URLError as exc:
            raise ImageGenerationError(
                f"Не удалось подключиться к OpenAI Image API: {exc.reason}"
            ) from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ImageGenerationError("OpenAI Image API вернул невалидный JSON.") from exc

        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise ImageGenerationError("OpenAI Image API не вернул image data.")

        b64_json = data[0].get("b64_json")
        if not isinstance(b64_json, str) or not b64_json.strip():
            raise ImageGenerationError("OpenAI Image API не вернул b64_json.")

        import base64

        return base64.b64decode(b64_json)


def cache_reference_images(
    *,
    posts_dataset: dict[str, Any],
    refs_dir: str | Path,
    limit: int = 5,
) -> dict[str, Any]:
    posts = posts_dataset.get("posts")
    if not isinstance(posts, list):
        raise ImageGenerationError("posts_dataset must contain a 'posts' list.")

    refs_dir = Path(refs_dir)
    refs_dir.mkdir(parents=True, exist_ok=True)

    cached_paths: list[str] = []
    failures: list[str] = []
    count = 0
    for index, post in enumerate(posts, start=1):
        image_url = post.get("image_url")
        if not isinstance(image_url, str) or not image_url.strip():
            continue
        target = refs_dir / f"reference_{index}.jpg"
        try:
            _download_public_file(image_url, target)
        except ImageGenerationError as exc:
            failures.append(str(exc))
            continue
        cached_paths.append(str(target))
        count += 1
        if count >= limit:
            break

    return {
        "cached_count": count,
        "cached_files": cached_paths,
        "failures": failures,
    }


def _build_image_prompt(*, draft: dict[str, Any]) -> str:
    title = draft.get("post_title") or ""
    hook = draft.get("hook") or ""
    asset = draft.get("asset_suggestion") or ""
    body_sections = draft.get("body_sections") or []
    if not isinstance(body_sections, list):
        body_sections = []

    return (
        "Create a LinkedIn post image in a visual direction similar to the provided reference images. "
        "Keep the composition clean, modern, SaaS-oriented, and suitable for a founder-led B2B LinkedIn feed. "
        "Do not include fabricated metrics, fake dashboards, or unreadable text blocks. "
        "Prefer a clear hero composition with subtle product/automation cues, light UI-inspired structure, and a polished but practical business feel. "
        f"Post title: {title}. "
        f"Hook: {hook}. "
        f"Key points: {' | '.join(str(x) for x in body_sections[:3])}. "
        f"Asset direction: {asset}."
    )


def _finalize_generation_prompt(
    *,
    generation_prompt: str,
    reference_analysis: dict[str, Any],
    visual_brief: dict[str, Any],
) -> str:
    locked_palette = ", ".join(str(x) for x in reference_analysis.get("locked_palette", []))
    locked_shapes = ", ".join(str(x) for x in reference_analysis.get("locked_shapes", []))
    locked_style_rules = ", ".join(str(x) for x in reference_analysis.get("locked_style_rules", []))
    optional_concept_patterns = ", ".join(
        str(x) for x in reference_analysis.get("optional_concept_patterns", [])
    )
    do_not_change = ", ".join(str(x) for x in visual_brief.get("do_not_change", []))
    visual_metaphor = str(visual_brief.get("best_visual_metaphor_for_this_post", ""))

    constraints = [
        "Stay максимально close to the reference image style.",
        "Do not introduce a new color palette if the references already establish one.",
        "Reuse the same visual mood, contrast logic, and overall aesthetic family from the references.",
        "Keep the composition simple and based on one dominant visual idea.",
        "Prefer a clean cover image, not an explainer diagram.",
        "Use one large top-centered title with 3 to 6 words maximum.",
        "Use only a very short subtitle or bottom caption when stylistically appropriate.",
        "Headline language must be directional and idea-led, not a hard measured claim, unless the claim is confirmed.",
        "Avoid tiny details, tiny labels, or dense small UI that will disappear at LinkedIn thumbnail size.",
        "Prefer two main silhouettes or two strong visual masses when possible.",
        "Avoid triptych, three-panel, step-by-step, process-diagram, flowchart, dashboard-collage, code-snippet, JSON-block, and UI-walkthrough layouts.",
        "Do not use a robot, mascot, human-vs-AI contrast, or character-led scene unless the chosen visual metaphor truly needs it.",
        "Do not use arrows or connectors as the primary structure of the image.",
        "Prefer one symbolic focal object or one clean product scene over narrative storytelling.",
        "Do not turn the image into an infographic, dashboard collage, busy split-screen, or side-by-side comparison unless the current visual metaphor truly requires it.",
        "Minimize text in the image.",
        "Preserve style, not composition copying.",
    ]
    if locked_palette:
        constraints.append(f"Locked palette: {locked_palette}.")
    if locked_shapes:
        constraints.append(f"Locked shape language: {locked_shapes}.")
    if locked_style_rules:
        constraints.append(f"Locked style rules: {locked_style_rules}.")
    if visual_metaphor:
        constraints.append(f"Best visual metaphor for this post: {visual_metaphor}.")
    if optional_concept_patterns:
        constraints.append(
            f"Optional concept patterns from references for inspiration only, not mandatory: {optional_concept_patterns}."
        )
    if do_not_change:
        constraints.append(f"Do not change: {do_not_change}.")

    headline_text = str(visual_brief.get("headline_text", "")).strip()
    subheadline_text = str(visual_brief.get("subheadline_text", "")).strip()
    left_label_text = str(visual_brief.get("left_label_text", "")).strip()
    right_label_text = str(visual_brief.get("right_label_text", "")).strip()
    bottom_caption_text = str(visual_brief.get("bottom_caption_text", "")).strip()
    if headline_text:
        constraints.append(f'Use this short in-image headline: "{headline_text}".')
    if subheadline_text:
        constraints.append(f'Optional tiny subtitle: "{subheadline_text}".')
    if left_label_text:
        constraints.append(f'Optional small left comparison label: "{left_label_text}".')
    if right_label_text:
        constraints.append(f'Optional small right comparison label: "{right_label_text}".')
    if bottom_caption_text:
        constraints.append(f'Optional bottom-center caption (6 to 9 words max): "{bottom_caption_text}".')

    return f"{generation_prompt} {' '.join(constraints)}"


def _normalize_reference_analysis(reference_analysis: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(reference_analysis)

    optional_patterns = list(normalized.get("optional_concept_patterns", []))
    locked_rules = []
    for item in normalized.get("locked_style_rules", []):
        text = str(item)
        lowered = text.lower()
        if any(
            phrase in lowered
            for phrase in (
                "split",
                "comparison",
                "flowchart",
                "diagram",
                "progression",
                "before/after",
                "before vs",
                "contrast",
            )
        ):
            optional_patterns.append(text)
            continue
        locked_rules.append(text)
    normalized["locked_style_rules"] = locked_rules

    visual_rules = []
    avoid = [str(item) for item in normalized.get("avoid", [])]
    for item in normalized.get("visual_rules", []):
        text = str(item)
        lowered = text.lower()
        if any(
            phrase in lowered
            for phrase in (
                "directional flow",
                "flow connector",
                "split",
                "comparison",
                "diagram",
                "flowchart",
                "arrows",
            )
        ):
            optional_patterns.append(text)
            continue
        visual_rules.append(text)
    normalized["visual_rules"] = visual_rules

    for forced_avoid in (
        "split-screen default layout",
        "comparison-first composition",
        "triptych or multi-panel storytelling",
        "arrow-led process composition",
    ):
        if forced_avoid not in avoid:
            avoid.append(forced_avoid)
    normalized["avoid"] = avoid
    normalized["optional_concept_patterns"] = list(dict.fromkeys(optional_patterns))
    return normalized


def _download_public_file(url: str, target: Path) -> None:
    req = request.Request(url, headers=DEFAULT_IMAGE_HEADERS, method="GET")
    try:
        with request.urlopen(req, timeout=60) as response:
            target.write_bytes(response.read())
    except error.HTTPError as exc:
        raise ImageGenerationError(
            f"Не удалось скачать reference image: {exc.code} {url}"
        ) from exc
    except error.URLError as exc:
        raise ImageGenerationError(
            f"Не удалось подключиться для скачивания reference image: {exc.reason}"
        ) from exc


def _select_image_size(reference_files: list[Path]) -> str:
    if not reference_files:
        return "1024x1024"

    landscape = 0
    portrait = 0
    square = 0

    for path in reference_files:
        size = _extract_dimensions_from_filename(path)
        if size is None:
            continue
        width, height = size
        if width > height:
            landscape += 1
        elif height > width:
            portrait += 1
        else:
            square += 1

    if landscape > max(portrait, square):
        return "1536x1024"
    if portrait > max(landscape, square):
        return "1024x1536"
    return "1024x1024"


def _extract_dimensions_from_filename(path: Path) -> tuple[int, int] | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None

    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return width, height

    if data.startswith(b"\xff\xd8"):
        index = 2
        data_len = len(data)
        while index < data_len - 1:
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            index += 2

            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > data_len:
                return None

            segment_length = int.from_bytes(data[index:index + 2], "big")
            if segment_length < 2 or index + segment_length > data_len:
                return None

            if marker in {
                0xC0, 0xC1, 0xC2, 0xC3,
                0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB,
                0xCD, 0xCE, 0xCF,
            }:
                if index + 7 > data_len:
                    return None
                height = int.from_bytes(data[index + 3:index + 5], "big")
                width = int.from_bytes(data[index + 5:index + 7], "big")
                return width, height

            index += segment_length

    return None


def _build_multipart_body(
    *,
    boundary: str,
    fields: list[tuple[str, str]],
    files: list[tuple[str, Path]],
) -> bytes:
    chunks: list[bytes] = []

    for name, value in fields:
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    for field_name, path in files:
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{field_name}"; '
                    f'filename="{path.name}"\r\n'
                ).encode(),
                f"Content-Type: {mime_type}\r\n\r\n".encode(),
                path.read_bytes(),
                b"\r\n",
            ]
        )

    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks)
