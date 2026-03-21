"""Console entrypoint for the Baltic Marketplace project."""

from __future__ import annotations

import argparse
import json
import sys
import termios
import tty
from pathlib import Path

from baltic_marketplace.analysis.drafts import (
    FactSafeDraftRefiner,
    FinalPolishRefiner,
    ImageHeadlineGenerator,
    LinkedInCompactRefiner,
    PostDraftGenerator,
)
from baltic_marketplace.analysis.posts import PostAnalyzer, load_dataset
from baltic_marketplace.analysis.recommendations import (
    NextPostRecommender,
    build_engagement_context,
    load_json,
)
from baltic_marketplace.apify.service import (
    DEFAULT_APIFY_ACTOR_ID,
    ApifyService,
    ApifyServiceError,
)
from baltic_marketplace.openai_api.service import DEFAULT_OPENAI_MODEL, OpenAIService, OpenAIServiceError
from baltic_marketplace.images.service import (
    DEFAULT_IMAGE_MODEL,
    ImageGenerationError,
    ImageGenerator,
    cache_reference_images,
)
from baltic_marketplace.storage import save_json

DEFAULT_LINKEDIN_PROFILE_URL = "https://www.linkedin.com/in/martin-liminovic-44046b21a/"
DEFAULT_OUTPUT_PATH = "data/linkedin_posts.json"
DEFAULT_ANALYSIS_PATH = "data/post_analysis.json"
DEFAULT_STRATEGY_PATH = "config/profile_strategy.json"
DEFAULT_RECOMMENDATION_PATH = "data/next_post_recommendation.json"
DEFAULT_DRAFT_PATH = "data/post_draft.json"
DEFAULT_SAFE_DRAFT_PATH = "data/post_draft_safe.json"
DEFAULT_COMPACT_DRAFT_PATH = "data/post_draft_compact.json"
DEFAULT_POLISHED_DRAFT_PATH = "data/post_draft_polished.json"
DEFAULT_IMAGE_HEADLINE_PATH = "data/post_image_headline.json"
DEFAULT_IMAGE_PATH = "data/generated_post_image.png"
DEFAULT_IMAGE_METADATA_PATH = "data/generated_post_image.json"
DEFAULT_IMAGE_REFS_DIR = "data/image_refs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baltic-marketplace",
        description="CLI for the Baltic Marketplace Apify pipeline.",
    )
    subparsers = parser.add_subparsers(dest="command")

    fetch_posts_apify = subparsers.add_parser(
        "fetch-posts-apify",
        help="Fetch public LinkedIn profile posts via Apify.",
    )
    fetch_posts_apify.add_argument(
        "--profile-url",
        default=DEFAULT_LINKEDIN_PROFILE_URL,
        help="LinkedIn profile URL to scrape.",
    )
    fetch_posts_apify.add_argument(
        "--max-posts",
        type=int,
        default=10,
        help="Maximum number of posts to request from the actor. Default: 10.",
    )
    fetch_posts_apify.add_argument(
        "--actor-id",
        help="Override Apify actor id. Example: scrapapi/linkedin-profile-post-scraper",
    )
    fetch_posts_apify.add_argument(
        "--out",
        default=DEFAULT_OUTPUT_PATH,
        help="Path to save normalized posts JSON.",
    )

    analyze_posts = subparsers.add_parser(
        "analyze-posts",
        help="Analyze saved LinkedIn posts with OpenAI API.",
    )
    analyze_posts.add_argument(
        "--input",
        default=DEFAULT_OUTPUT_PATH,
        help="Path to normalized posts JSON.",
    )
    analyze_posts.add_argument(
        "--out",
        default=DEFAULT_ANALYSIS_PATH,
        help="Path to save structured analysis JSON.",
    )
    analyze_posts.add_argument(
        "--model",
        default=DEFAULT_OPENAI_MODEL,
        help="OpenAI model to use for analysis.",
    )

    recommend_next_post = subparsers.add_parser(
        "recommend-next-post",
        help="Recommend the next LinkedIn post using analysis + strategy.",
    )
    recommend_next_post.add_argument(
        "--analysis",
        default=DEFAULT_ANALYSIS_PATH,
        help="Path to structured post analysis JSON.",
    )
    recommend_next_post.add_argument(
        "--strategy",
        default=DEFAULT_STRATEGY_PATH,
        help="Path to profile strategy JSON.",
    )
    recommend_next_post.add_argument(
        "--posts",
        default=DEFAULT_OUTPUT_PATH,
        help="Path to normalized LinkedIn posts JSON for engagement context.",
    )
    recommend_next_post.add_argument(
        "--out",
        default=DEFAULT_RECOMMENDATION_PATH,
        help="Path to save next post recommendation JSON.",
    )
    recommend_next_post.add_argument(
        "--model",
        default=DEFAULT_OPENAI_MODEL,
        help="OpenAI model to use for recommendation.",
    )

    generate_post_draft = subparsers.add_parser(
        "generate-post-draft",
        help="Generate a LinkedIn post draft from the recommendation layer.",
    )
    generate_post_draft.add_argument(
        "--analysis",
        default=DEFAULT_ANALYSIS_PATH,
        help="Path to structured post analysis JSON.",
    )
    generate_post_draft.add_argument(
        "--strategy",
        default=DEFAULT_STRATEGY_PATH,
        help="Path to profile strategy JSON.",
    )
    generate_post_draft.add_argument(
        "--recommendation",
        default=DEFAULT_RECOMMENDATION_PATH,
        help="Path to next post recommendation JSON.",
    )
    generate_post_draft.add_argument(
        "--posts",
        default=DEFAULT_OUTPUT_PATH,
        help="Path to normalized LinkedIn posts JSON for engagement context.",
    )
    generate_post_draft.add_argument(
        "--out",
        default=DEFAULT_DRAFT_PATH,
        help="Path to save generated post draft JSON.",
    )
    generate_post_draft.add_argument(
        "--model",
        default=DEFAULT_OPENAI_MODEL,
        help="OpenAI model to use for draft generation.",
    )

    refine_post_draft = subparsers.add_parser(
        "refine-post-draft",
        help="Refine a generated draft into a fact-safe version.",
    )
    refine_post_draft.add_argument(
        "--draft",
        default=DEFAULT_DRAFT_PATH,
        help="Path to generated post draft JSON.",
    )
    refine_post_draft.add_argument(
        "--strategy",
        default=DEFAULT_STRATEGY_PATH,
        help="Path to profile strategy JSON.",
    )
    refine_post_draft.add_argument(
        "--recommendation",
        default=DEFAULT_RECOMMENDATION_PATH,
        help="Path to next post recommendation JSON.",
    )
    refine_post_draft.add_argument(
        "--posts",
        default=DEFAULT_OUTPUT_PATH,
        help="Path to normalized LinkedIn posts JSON for engagement context.",
    )
    refine_post_draft.add_argument(
        "--out",
        default=DEFAULT_SAFE_DRAFT_PATH,
        help="Path to save fact-safe post draft JSON.",
    )
    refine_post_draft.add_argument(
        "--model",
        default=DEFAULT_OPENAI_MODEL,
        help="OpenAI model to use for fact-safe refinement.",
    )

    compact_post_draft = subparsers.add_parser(
        "compact-post-draft",
        help="Compress the safe draft into a sharper LinkedIn-ready version.",
    )
    compact_post_draft.add_argument(
        "--draft",
        default=DEFAULT_SAFE_DRAFT_PATH,
        help="Path to fact-safe post draft JSON.",
    )
    compact_post_draft.add_argument(
        "--strategy",
        default=DEFAULT_STRATEGY_PATH,
        help="Path to profile strategy JSON.",
    )
    compact_post_draft.add_argument(
        "--recommendation",
        default=DEFAULT_RECOMMENDATION_PATH,
        help="Path to next post recommendation JSON.",
    )
    compact_post_draft.add_argument(
        "--posts",
        default=DEFAULT_OUTPUT_PATH,
        help="Path to normalized LinkedIn posts JSON for engagement context.",
    )
    compact_post_draft.add_argument(
        "--out",
        default=DEFAULT_COMPACT_DRAFT_PATH,
        help="Path to save compact post draft JSON.",
    )
    compact_post_draft.add_argument(
        "--model",
        default=DEFAULT_OPENAI_MODEL,
        help="OpenAI model to use for compact refinement.",
    )

    final_polish_draft = subparsers.add_parser(
        "final-polish-draft",
        help="Apply final publish-ready polish to the compact draft.",
    )
    final_polish_draft.add_argument("--draft", default=DEFAULT_COMPACT_DRAFT_PATH)
    final_polish_draft.add_argument("--strategy", default=DEFAULT_STRATEGY_PATH)
    final_polish_draft.add_argument("--recommendation", default=DEFAULT_RECOMMENDATION_PATH)
    final_polish_draft.add_argument("--posts", default=DEFAULT_OUTPUT_PATH)
    final_polish_draft.add_argument("--out", default=DEFAULT_POLISHED_DRAFT_PATH)
    final_polish_draft.add_argument("--model", default=DEFAULT_OPENAI_MODEL)

    generate_image_headline = subparsers.add_parser(
        "generate-image-headline",
        help="Generate a dedicated headline/subheadline pair for the cover image.",
    )
    generate_image_headline.add_argument("--draft", default=DEFAULT_POLISHED_DRAFT_PATH)
    generate_image_headline.add_argument("--strategy", default=DEFAULT_STRATEGY_PATH)
    generate_image_headline.add_argument("--recommendation", default=DEFAULT_RECOMMENDATION_PATH)
    generate_image_headline.add_argument("--posts", default=DEFAULT_OUTPUT_PATH)
    generate_image_headline.add_argument("--out", default=DEFAULT_IMAGE_HEADLINE_PATH)
    generate_image_headline.add_argument("--model", default=DEFAULT_OPENAI_MODEL)

    generate_post_image = subparsers.add_parser(
        "generate-post-image",
        help="Generate a post image using past post images as style references.",
    )
    generate_post_image.add_argument(
        "--draft",
        default=DEFAULT_POLISHED_DRAFT_PATH,
        help="Path to fact-safe post draft JSON.",
    )
    generate_post_image.add_argument(
        "--posts",
        default=DEFAULT_OUTPUT_PATH,
        help="Path to normalized LinkedIn posts JSON.",
    )
    generate_post_image.add_argument(
        "--out",
        default=DEFAULT_IMAGE_PATH,
        help="Path to save generated image PNG.",
    )
    generate_post_image.add_argument(
        "--metadata-out",
        default=DEFAULT_IMAGE_METADATA_PATH,
        help="Path to save image generation metadata JSON.",
    )
    generate_post_image.add_argument(
        "--refs-dir",
        default=DEFAULT_IMAGE_REFS_DIR,
        help="Directory for downloaded reference images.",
    )
    generate_post_image.add_argument(
        "--model",
        default=DEFAULT_IMAGE_MODEL,
        help="OpenAI image model to use.",
    )

    run_full_pipeline = subparsers.add_parser(
        "run-full-pipeline",
        help="Run the full LinkedIn assistant pipeline from ingest to image generation.",
    )
    run_full_pipeline.add_argument(
        "--max-posts",
        type=int,
        default=10,
        help="Maximum number of posts to fetch from Apify. Default: 10.",
    )
    run_full_pipeline.add_argument(
        "--text-model",
        default=DEFAULT_OPENAI_MODEL,
        help="OpenAI text model to use for analysis, recommendation, and drafting.",
    )
    run_full_pipeline.add_argument(
        "--image-model",
        default=DEFAULT_IMAGE_MODEL,
        help="OpenAI image model to use for image generation.",
    )

    return parser


def main() -> int:
    if len(sys.argv) == 1:
        return run_interactive_menu()

    parser = build_parser()
    args = parser.parse_args()

    if args.command == "fetch-posts-apify":
        try:
            service = ApifyService.from_env(default_actor_id=args.actor_id)
            payload = service.fetch_linkedin_profile_post_dataset(
                profile_url=args.profile_url,
                max_posts=args.max_posts,
            )
            refs_cache = cache_reference_images(
                posts_dataset=payload,
                refs_dir=DEFAULT_IMAGE_REFS_DIR,
            )
        except ApifyServiceError as exc:
            parser.exit(status=1, message=f"error: {exc}\n")
        except ImageGenerationError as exc:
            parser.exit(status=1, message=f"error: {exc}\n")

        saved_path = save_json(args.out, payload)
        print(f"Saved to {saved_path}")
        print(f"Cached reference images: {refs_cache['cached_count']}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "analyze-posts":
        try:
            dataset = load_dataset(args.input)
            analyzer = PostAnalyzer(OpenAIService.from_env(default_model=args.model))
            payload = analyzer.analyze_dataset(dataset)
        except (OpenAIServiceError, ValueError, OSError, json.JSONDecodeError) as exc:
            parser.exit(status=1, message=f"error: {exc}\n")

        saved_path = save_json(args.out, payload)
        print(f"Saved to {saved_path}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "recommend-next-post":
        try:
            post_analysis = load_json(args.analysis)
            profile_strategy = load_json(args.strategy)
            posts_dataset = load_json(args.posts)
            engagement_context = build_engagement_context(
                posts_dataset=posts_dataset,
                post_analysis=post_analysis,
            )
            recommender = NextPostRecommender(
                OpenAIService.from_env(default_model=args.model)
            )
            payload = recommender.recommend(
                post_analysis=post_analysis,
                profile_strategy=profile_strategy,
                engagement_context=engagement_context,
            )
        except (OpenAIServiceError, ValueError, OSError, json.JSONDecodeError) as exc:
            parser.exit(status=1, message=f"error: {exc}\n")

        saved_path = save_json(args.out, payload)
        print(f"Saved to {saved_path}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "generate-post-draft":
        try:
            post_analysis = load_json(args.analysis)
            profile_strategy = load_json(args.strategy)
            recommendation = load_json(args.recommendation)
            posts_dataset = load_json(args.posts)
            engagement_context = build_engagement_context(
                posts_dataset=posts_dataset,
                post_analysis=post_analysis,
            )
            generator = PostDraftGenerator(
                OpenAIService.from_env(default_model=args.model)
            )
            payload = generator.generate(
                post_analysis=post_analysis,
                profile_strategy=profile_strategy,
                recommendation=recommendation,
                engagement_context=engagement_context,
            )
        except (OpenAIServiceError, ValueError, OSError, json.JSONDecodeError) as exc:
            parser.exit(status=1, message=f"error: {exc}\n")

        saved_path = save_json(args.out, payload)
        print(f"Saved to {saved_path}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "refine-post-draft":
        try:
            draft_payload = load_json(args.draft)
            profile_strategy = load_json(args.strategy)
            recommendation = load_json(args.recommendation)
            posts_dataset = load_json(args.posts)
            post_analysis = load_json(DEFAULT_ANALYSIS_PATH)
            engagement_context = build_engagement_context(
                posts_dataset=posts_dataset,
                post_analysis=post_analysis,
            )
            refiner = FactSafeDraftRefiner(
                OpenAIService.from_env(default_model=args.model)
            )
            payload = refiner.refine(
                draft_payload=draft_payload,
                profile_strategy=profile_strategy,
                recommendation=recommendation,
                engagement_context=engagement_context,
            )
        except (OpenAIServiceError, ValueError, OSError, json.JSONDecodeError) as exc:
            parser.exit(status=1, message=f"error: {exc}\n")

        saved_path = save_json(args.out, payload)
        print(f"Saved to {saved_path}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "compact-post-draft":
        try:
            draft_payload = load_json(args.draft)
            profile_strategy = load_json(args.strategy)
            recommendation = load_json(args.recommendation)
            posts_dataset = load_json(args.posts)
            post_analysis = load_json(DEFAULT_ANALYSIS_PATH)
            engagement_context = build_engagement_context(
                posts_dataset=posts_dataset,
                post_analysis=post_analysis,
            )
            refiner = LinkedInCompactRefiner(
                OpenAIService.from_env(default_model=args.model)
            )
            payload = refiner.refine(
                draft_payload=draft_payload,
                profile_strategy=profile_strategy,
                recommendation=recommendation,
                engagement_context=engagement_context,
            )
        except (OpenAIServiceError, ValueError, OSError, json.JSONDecodeError) as exc:
            parser.exit(status=1, message=f"error: {exc}\n")

        saved_path = save_json(args.out, payload)
        print(f"Saved to {saved_path}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "final-polish-draft":
        try:
            draft_payload = load_json(args.draft)
            profile_strategy = load_json(args.strategy)
            recommendation = load_json(args.recommendation)
            posts_dataset = load_json(args.posts)
            post_analysis = load_json(DEFAULT_ANALYSIS_PATH)
            engagement_context = build_engagement_context(
                posts_dataset=posts_dataset,
                post_analysis=post_analysis,
            )
            refiner = FinalPolishRefiner(OpenAIService.from_env(default_model=args.model))
            payload = refiner.refine(
                draft_payload=draft_payload,
                profile_strategy=profile_strategy,
                recommendation=recommendation,
                engagement_context=engagement_context,
            )
        except (OpenAIServiceError, ValueError, OSError, json.JSONDecodeError) as exc:
            parser.exit(status=1, message=f"error: {exc}\n")

        saved_path = save_json(args.out, payload)
        print(f"Saved to {saved_path}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "generate-image-headline":
        try:
            draft_payload = load_json(args.draft)
            profile_strategy = load_json(args.strategy)
            recommendation = load_json(args.recommendation)
            posts_dataset = load_json(args.posts)
            post_analysis = load_json(DEFAULT_ANALYSIS_PATH)
            engagement_context = build_engagement_context(
                posts_dataset=posts_dataset,
                post_analysis=post_analysis,
            )
            generator = ImageHeadlineGenerator(OpenAIService.from_env(default_model=args.model))
            payload = generator.generate(
                draft_payload=draft_payload,
                profile_strategy=profile_strategy,
                recommendation=recommendation,
                engagement_context=engagement_context,
            )
        except (OpenAIServiceError, ValueError, OSError, json.JSONDecodeError) as exc:
            parser.exit(status=1, message=f"error: {exc}\n")

        saved_path = save_json(args.out, payload)
        print(f"Saved to {saved_path}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "generate-post-image":
        try:
            draft_payload = load_json(args.draft)
            posts_dataset = load_json(args.posts)
            generator = ImageGenerator.from_env(default_model=args.model)
            payload = generator.create_post_image(
                draft_payload=draft_payload,
                posts_dataset=posts_dataset,
                refs_dir=args.refs_dir,
                output_path=args.out,
                metadata_path=args.metadata_out,
            )
        except (ImageGenerationError, OSError, json.JSONDecodeError, ValueError) as exc:
            parser.exit(status=1, message=f"error: {exc}\n")

        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-full-pipeline":
        try:
            payload = _run_full_pipeline(
                max_posts=args.max_posts,
                text_model=args.text_model,
                image_model=args.image_model,
            )
        except (
            ApifyServiceError,
            OpenAIServiceError,
            ImageGenerationError,
            ValueError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            parser.exit(status=1, message=f"error: {exc}\n")

        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("Baltic Marketplace CLI is ready.")
    return 0


def run_interactive_menu() -> int:
    menu_items = [("Fetch profile posts via Apify", _run_apify_menu_action), ("Exit", None)]

    if sys.stdin.isatty() and sys.stdout.isatty():
        return _run_arrow_menu(menu_items)

    while True:
        print()
        print("Baltic Marketplace CLI")
        print("1. Fetch profile posts via Apify")
        print("0. Exit")

        choice = input("Choose an action: ").strip()
        print()

        if choice == "0":
            print("Exit.")
            return 0

        if choice == "1":
            _run_apify_menu_action()
            continue

        print("Unknown menu item. Enter 0 or 1.")


def _run_apify_menu_action() -> None:
    max_posts_raw = input("How many posts to fetch [10]: ").strip()

    max_posts = _parse_positive_int(max_posts_raw, default=10, field_name="max-posts")
    if max_posts is None:
        return

    try:
        service = ApifyService.from_env(default_actor_id=DEFAULT_APIFY_ACTOR_ID)
        dataset = service.fetch_linkedin_profile_post_dataset(
            profile_url=DEFAULT_LINKEDIN_PROFILE_URL,
            max_posts=max_posts,
        )
        refs_cache = cache_reference_images(
            posts_dataset=dataset,
            refs_dir=DEFAULT_IMAGE_REFS_DIR,
        )
        summaries = service.fetch_linkedin_profile_post_summaries(
            profile_url=DEFAULT_LINKEDIN_PROFILE_URL,
            max_posts=max_posts,
        )
    except (ApifyServiceError, ImageGenerationError) as exc:
        print(f"error: {exc}")
        return

    saved_path = save_json(DEFAULT_OUTPUT_PATH, dataset)
    print(f"Saved to {Path(saved_path)}")
    print(f"Cached reference images: {refs_cache['cached_count']}")
    print()
    _print_post_summaries(summaries)


def _parse_positive_int(
    value: str,
    *,
    default: int,
    field_name: str,
) -> int | None:
    if not value:
        return default

    try:
        parsed = int(value)
    except ValueError:
        print(f"error: {field_name} must be an integer.")
        return None

    if parsed < 1:
        print(f"error: {field_name} must be greater than 0.")
        return None

    return parsed


def _run_arrow_menu(menu_items: list[tuple[str, object | None]]) -> int:
    selected_index = 0

    while True:
        _render_arrow_menu(menu_items, selected_index)
        key = _read_menu_key()

        if key == "up":
            selected_index = (selected_index - 1) % len(menu_items)
            continue

        if key == "down":
            selected_index = (selected_index + 1) % len(menu_items)
            continue

        if key != "enter":
            continue

        label, action = menu_items[selected_index]
        _clear_screen()
        if label == "Exit":
            print("Exit.")
            return 0

        assert callable(action)
        print(f"Selected: {label}")
        print()
        action()
        try:
            input("\nPress Enter to return to the menu...")
        except KeyboardInterrupt:
            print()


def _render_arrow_menu(
    menu_items: list[tuple[str, object | None]],
    selected_index: int,
) -> None:
    _clear_screen()
    print("Baltic Marketplace CLI")
    print("Use Up/Down arrows and Enter.\n")

    for index, (label, _) in enumerate(menu_items):
        prefix = ">" if index == selected_index else " "
        print(f"{prefix} {label}")


def _read_menu_key() -> str:
    fd = sys.stdin.fileno()
    original_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        first = sys.stdin.read(1)
        if first == "\x1b":
            second = sys.stdin.read(1)
            third = sys.stdin.read(1)
            if second == "[" and third == "A":
                return "up"
            if second == "[" and third == "B":
                return "down"
            return "other"
        if first in ("\r", "\n"):
            return "enter"
        return "other"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original_settings)


def _clear_screen() -> None:
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def _print_post_summaries(summaries: list[dict[str, object]]) -> None:
    if not summaries:
        print("No posts found.")
        return

    for index, summary in enumerate(summaries, start=1):
        print(f"Post {index}")
        print(f"Text: {summary.get('text') or ''}")
        print(f"Likes: {summary.get('likes') or 0}")
        print(f"Comments: {summary.get('comments') or 0}")
        print(f"Image URL: {summary.get('image_url') or '-'}")
        if index != len(summaries):
            print()


def _run_full_pipeline(
    *,
    max_posts: int,
    text_model: str,
    image_model: str,
) -> dict[str, object]:
    _print_stage(1, 9, "Fetching posts from Apify", "Pulling latest posts and refreshing local references")
    apify = ApifyService.from_env(default_actor_id=DEFAULT_APIFY_ACTOR_ID)
    posts_dataset = apify.fetch_linkedin_profile_post_dataset(
        profile_url=DEFAULT_LINKEDIN_PROFILE_URL,
        max_posts=max_posts,
    )
    save_json(DEFAULT_OUTPUT_PATH, posts_dataset)
    refs_cache = cache_reference_images(
        posts_dataset=posts_dataset,
        refs_dir=DEFAULT_IMAGE_REFS_DIR,
    )
    print(f"Cached reference images: {refs_cache['cached_count']}")

    _print_stage(2, 9, "Analyzing posts", "Reducing posts into themes, hooks, CTAs, and pattern signals")
    llm = OpenAIService.from_env(default_model=text_model)
    post_analysis = PostAnalyzer(llm).analyze_dataset(posts_dataset)
    save_json(DEFAULT_ANALYSIS_PATH, post_analysis)

    _print_stage(3, 9, "Building recommendation", "Combining post analysis with profile strategy")
    profile_strategy = load_json(DEFAULT_STRATEGY_PATH)
    recommendation = NextPostRecommender(llm).recommend(
        post_analysis=post_analysis,
        profile_strategy=profile_strategy,
        engagement_context=build_engagement_context(
            posts_dataset=posts_dataset,
            post_analysis=post_analysis,
        ),
    )
    save_json(DEFAULT_RECOMMENDATION_PATH, recommendation)

    _print_stage(4, 9, "Generating draft", "Writing the next post based on the chosen direction")
    engagement_context = build_engagement_context(
        posts_dataset=posts_dataset,
        post_analysis=post_analysis,
    )
    draft = PostDraftGenerator(llm).generate(
        post_analysis=post_analysis,
        profile_strategy=profile_strategy,
        recommendation=recommendation,
        engagement_context=engagement_context,
    )
    save_json(DEFAULT_DRAFT_PATH, draft)

    _print_stage(5, 9, "Refining fact-safe draft", "Removing unsupported claims and softening risky phrasing")
    safe_draft = FactSafeDraftRefiner(llm).refine(
        draft_payload=draft,
        profile_strategy=profile_strategy,
        recommendation=recommendation,
        engagement_context=engagement_context,
    )
    save_json(DEFAULT_SAFE_DRAFT_PATH, safe_draft)

    _print_stage(6, 9, "Compacting draft", "Compressing the safe draft into a sharper LinkedIn-ready version")
    compact_draft = LinkedInCompactRefiner(llm).refine(
        draft_payload=safe_draft,
        profile_strategy=profile_strategy,
        recommendation=recommendation,
        engagement_context=engagement_context,
    )
    save_json(DEFAULT_COMPACT_DRAFT_PATH, compact_draft)

    _print_stage(7, 9, "Final polish", "Making the draft sound more natural and publish-ready")
    polished_draft = FinalPolishRefiner(llm).refine(
        draft_payload=compact_draft,
        profile_strategy=profile_strategy,
        recommendation=recommendation,
        engagement_context=engagement_context,
    )
    save_json(DEFAULT_POLISHED_DRAFT_PATH, polished_draft)

    _print_stage(8, 9, "Image headline", "Generating a dedicated cover headline and subtitle")
    image_headline_payload = ImageHeadlineGenerator(llm).generate(
        draft_payload=polished_draft,
        profile_strategy=profile_strategy,
        recommendation=recommendation,
        engagement_context=engagement_context,
    )
    save_json(DEFAULT_IMAGE_HEADLINE_PATH, image_headline_payload)
    polished_draft_for_image = json.loads(json.dumps(polished_draft))
    polished_draft_for_image.setdefault("draft", {})
    polished_draft_for_image["draft"]["image_headline"] = image_headline_payload.get("image_headline", "")
    polished_draft_for_image["draft"]["image_subheadline"] = image_headline_payload.get("image_subheadline", "")
    save_json(DEFAULT_POLISHED_DRAFT_PATH, polished_draft_for_image)

    _print_stage(9, 9, "Generating image", "Analyzing reference visuals, building a visual brief, and rendering the final asset")
    image_metadata = ImageGenerator.from_env(default_model=image_model).create_post_image(
        draft_payload=polished_draft_for_image,
        posts_dataset=posts_dataset,
        refs_dir=DEFAULT_IMAGE_REFS_DIR,
        output_path=DEFAULT_IMAGE_PATH,
        metadata_path=DEFAULT_IMAGE_METADATA_PATH,
    )

    print("Pipeline completed.")
    return {
        "status": "ok",
        "outputs": {
            "posts": DEFAULT_OUTPUT_PATH,
            "analysis": DEFAULT_ANALYSIS_PATH,
            "recommendation": DEFAULT_RECOMMENDATION_PATH,
            "draft": DEFAULT_DRAFT_PATH,
            "safe_draft": DEFAULT_SAFE_DRAFT_PATH,
            "compact_draft": DEFAULT_COMPACT_DRAFT_PATH,
            "polished_draft": DEFAULT_POLISHED_DRAFT_PATH,
            "image_headline": DEFAULT_IMAGE_HEADLINE_PATH,
            "image": DEFAULT_IMAGE_PATH,
            "image_metadata": DEFAULT_IMAGE_METADATA_PATH,
        },
        "image_metadata": image_metadata,
    }


def _print_stage(step: int, total: int, title: str, detail: str) -> None:
    print(f"Step {step}/{total}: {title}...")
    print(f"  {detail}")
