"""CLI for broad Upwork market collection."""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
from pathlib import Path

from baltic_marketplace.services.apify import ApifyService, ApifyServiceError
from baltic_marketplace.services.openai import OpenAIService, OpenAIServiceError
from baltic_marketplace.services.upwork import (
    DEFAULT_SEARCH_QUERY,
    DEFAULT_PAGE_SIZE,
    UpworkService,
    UpworkServiceError,
)


DEFAULT_WEB_DEVELOPMENT_CATEGORY = "Web Development"
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "have",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "we",
    "with",
    "you",
    "your",
}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="baltic-marketplace")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser(
        "collect-web-development-jobs",
        help="Collect a broad Upwork corpus for the Web Development category in a single run.",
    )
    collect_parser.add_argument(
        "--limit",
        type=int,
        default=6000,
        help="Maximum number of jobs to request in one run. Default: 6000",
    )
    collect_parser.add_argument(
        "--output",
        default="data/web_development.json",
        help="Path to output JSON file.",
    )
    collect_parser.set_defaults(func=collect_web_development_jobs_command)

    upwork_collect_parser = subparsers.add_parser(
        "collect-upwork-jobs",
        help="Collect Upwork marketplace jobs via the official Upwork GraphQL API.",
    )
    upwork_collect_parser.add_argument(
        "--query",
        default=DEFAULT_SEARCH_QUERY,
        help=f'Search query for Upwork marketplace jobs. Default: "{DEFAULT_SEARCH_QUERY}"',
    )
    upwork_collect_parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum number of jobs to request. Default: 200",
    )
    upwork_collect_parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f"Page size per Upwork API request. Default: {DEFAULT_PAGE_SIZE}",
    )
    upwork_collect_parser.add_argument(
        "--output",
        default="data/web_development.json",
        help="Path to output JSON file.",
    )
    upwork_collect_parser.set_defaults(func=collect_upwork_jobs_command)

    freq_parser = subparsers.add_parser(
        "show-market-top-frequencies",
        help="Read saved job corpus and print top title/description phrases for segmentation, with skills as validation.",
    )
    freq_parser.add_argument(
        "--input",
        default="data/web_development.json",
        help="Path to source JSON file.",
    )
    freq_parser.add_argument(
        "--top",
        type=int,
        default=50,
        help="How many top items to print per section. Default: 50",
    )
    freq_parser.add_argument(
        "--min-word-length",
        type=int,
        default=4,
        help="Minimum word length for title/description phrase tokens. Default: 4",
    )
    freq_parser.add_argument(
        "--skills-output",
        default="data/pattern_layer/skills.csv",
        help="Path to skills frequency CSV file. Default: data/pattern_layer/skills.csv",
    )
    freq_parser.add_argument(
        "--title-output",
        default="data/pattern_layer/title.csv",
        help="Path to title patterns CSV file. Default: data/pattern_layer/title.csv",
    )
    freq_parser.add_argument(
        "--description-output",
        default="data/pattern_layer/description.csv",
        help="Path to description patterns CSV file. Default: data/pattern_layer/description.csv",
    )
    freq_parser.set_defaults(func=show_market_top_frequencies_command)

    normalize_parser = subparsers.add_parser(
        "normalize-market-patterns",
        help="Normalize title and description pattern CSV files using lowercase and special-character unification.",
    )
    normalize_parser.add_argument(
        "--title-input",
        default="data/pattern_layer/title.csv",
        help="Path to source title patterns CSV file. Default: data/pattern_layer/title.csv",
    )
    normalize_parser.add_argument(
        "--description-input",
        default="data/pattern_layer/description.csv",
        help="Path to source description patterns CSV file. Default: data/pattern_layer/description.csv",
    )
    normalize_parser.add_argument(
        "--title-output",
        default="data/normalizer_layer/title.csv",
        help="Path to normalized title patterns CSV file. Default: data/normalizer_layer/title.csv",
    )
    normalize_parser.add_argument(
        "--description-output",
        default="data/normalizer_layer/description.csv",
        help="Path to normalized description patterns CSV file. Default: data/normalizer_layer/description.csv",
    )
    normalize_parser.set_defaults(func=normalize_market_patterns_command)

    classify_parser = subparsers.add_parser(
        "classify-market-patterns",
        help="Use OpenAI to classify market patterns into segment signals, supporting signals, boilerplate, and noise.",
    )
    classify_parser.add_argument(
        "--input",
        default="data/market_top_frequencies_evidence.json",
        help="Path to evidence JSON file. Default: data/market_top_frequencies_evidence.json",
    )
    classify_parser.add_argument(
        "--output",
        default="data/market_pattern_classification.json",
        help="Path to output classification JSON. Default: data/market_pattern_classification.json",
    )
    classify_parser.add_argument(
        "--max-patterns-per-section",
        type=int,
        default=20,
        help="Maximum number of patterns to send to the LLM per section. Default: 20",
    )
    classify_parser.add_argument(
        "--max-job-ids-per-pattern",
        type=int,
        default=3,
        help="Maximum number of job ids to attach to each pattern. Default: 3",
    )
    classify_parser.set_defaults(func=classify_market_patterns_command)

    reverse_parser = subparsers.add_parser(
        "build-unique-job-pattern-hits",
        help="Build reverse mapping from unique job ids to the market patterns they matched.",
    )
    reverse_parser.add_argument(
        "--input",
        default="data/market_top_frequencies_evidence.json",
        help="Path to evidence JSON file. Default: data/market_top_frequencies_evidence.json",
    )
    reverse_parser.add_argument(
        "--output",
        default="data/unique_jobs_with_pattern_hits.json",
        help="Path to output reverse-mapping JSON. Default: data/unique_jobs_with_pattern_hits.json",
    )
    reverse_parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.8,
        help="Weighted similarity threshold for collapsing similar jobs into a cluster. Default: 0.8",
    )
    reverse_parser.set_defaults(func=build_unique_job_pattern_hits_command)

    return parser


def collect_web_development_jobs_command(args: argparse.Namespace) -> int:
    if args.limit < 1:
        raise SystemExit("limit должен быть больше 0.")

    try:
        service = ApifyService.from_env()
    except ApifyServiceError as exc:
        raise SystemExit(str(exc)) from exc

    try:
        result = service.collect_upwork_jobs(
            limit=args.limit,
            job_categories=[DEFAULT_WEB_DEVELOPMENT_CATEGORY],
        )
    except ApifyServiceError as exc:
        raise SystemExit(str(exc)) from exc

    items = result.get("items", [])
    if not isinstance(items, list):
        raise SystemExit("Apify service вернул неожиданный формат items.")

    unique_items: list[dict[str, object]] = []
    seen_keys: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        dedupe_key = _job_dedupe_key(item)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        unique_items.append(item)

    output_payload = {
        "source": "apify",
        "category": DEFAULT_WEB_DEVELOPMENT_CATEGORY,
        "requested_limit": args.limit,
        "raw_count": len(items),
        "unique_count": len(unique_items),
        "input": result.get("input", {}),
        "items": unique_items,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Requested limit: {args.limit}")
    print(f"Raw jobs: {len(items)}")
    print(f"Unique jobs: {len(unique_items)}")
    print(f"Saved JSON: {output_path}")
    return 0


def collect_upwork_jobs_command(args: argparse.Namespace) -> int:
    if args.limit < 1:
        raise SystemExit("limit должен быть больше 0.")
    if args.page_size < 1:
        raise SystemExit("page-size должен быть больше 0.")

    try:
        service = UpworkService.from_env()
    except UpworkServiceError as exc:
        raise SystemExit(str(exc)) from exc

    try:
        result = service.collect_marketplace_jobs(
            search_query=args.query,
            limit=args.limit,
            page_size=args.page_size,
        )
    except UpworkServiceError as exc:
        raise SystemExit(str(exc)) from exc

    items = result.get("items", [])
    if not isinstance(items, list):
        raise SystemExit("Upwork service вернул неожиданный формат items.")

    unique_items: list[dict[str, object]] = []
    seen_keys: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        dedupe_key = _job_dedupe_key(item)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        unique_items.append(item)

    output_payload = {
        "source": "upwork",
        "query": args.query,
        "requested_limit": args.limit,
        "raw_count": len(items),
        "unique_count": len(unique_items),
        "items": unique_items,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f'Search query: "{args.query}"')
    print(f"Requested limit: {args.limit}")
    print(f"Raw jobs: {len(items)}")
    print(f"Unique jobs: {len(unique_items)}")
    print(f"Saved JSON: {output_path}")
    return 0


def show_market_top_frequencies_command(args: argparse.Namespace) -> int:
    if args.top < 1:
        raise SystemExit("top должен быть больше 0.")
    if args.min_word_length < 1:
        raise SystemExit("min-word-length должен быть больше 0.")

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Файл не найден: {input_path}")

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise SystemExit("В JSON нет корректного списка items.")

    skill_counts: collections.Counter[str] = collections.Counter()
    title_bigram_counts: collections.Counter[str] = collections.Counter()
    title_trigram_counts: collections.Counter[str] = collections.Counter()
    description_bigram_counts: collections.Counter[str] = collections.Counter()
    description_trigram_counts: collections.Counter[str] = collections.Counter()
    for item in items:
        if not isinstance(item, dict):
            continue

        skills = item.get("skills") or []
        if isinstance(skills, list):
            for skill in skills:
                skill_name = str(skill).strip()
                if skill_name:
                    skill_counts[skill_name] += 1

        title = item.get("title")
        if isinstance(title, str):
            title_words = _extract_words(title, min_length=args.min_word_length)
            for phrase in _extract_ngrams(title_words, 2):
                title_bigram_counts[phrase] += 1
            for phrase in _extract_ngrams(title_words, 3):
                title_trigram_counts[phrase] += 1

        description = item.get("description")
        if isinstance(description, str):
            description_words = _extract_words(description, min_length=args.min_word_length)
            for phrase in _extract_ngrams(description_words, 2):
                description_bigram_counts[phrase] += 1
            for phrase in _extract_ngrams(description_words, 3):
                description_trigram_counts[phrase] += 1

    print("=== Top Title Bigrams ===")
    for phrase, count in title_bigram_counts.most_common(args.top):
        print(f"{phrase}\t{count}")

    print("\n=== Top Title Trigrams ===")
    for phrase, count in title_trigram_counts.most_common(args.top):
        print(f"{phrase}\t{count}")

    print("\n=== Top Description Bigrams ===")
    for phrase, count in description_bigram_counts.most_common(args.top):
        print(f"{phrase}\t{count}")

    print("\n=== Top Description Trigrams ===")
    for phrase, count in description_trigram_counts.most_common(args.top):
        print(f"{phrase}\t{count}")

    print("\n=== Top Skills (Validation Layer) ===")
    for skill, count in skill_counts.most_common(args.top):
        print(f"{skill}\t{count}")

    skills_rows = _build_count_rows(skill_counts, args.top)
    title_rows = _build_pattern_rows(
        bigrams=title_bigram_counts,
        trigrams=title_trigram_counts,
        top=args.top,
    )
    description_rows = _build_pattern_rows(
        bigrams=description_bigram_counts,
        trigrams=description_trigram_counts,
        top=args.top,
    )

    skills_path = Path(args.skills_output)
    skills_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(skills_path, fieldnames=["value", "count"], rows=skills_rows)

    title_path = Path(args.title_output)
    title_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(title_path, fieldnames=["pattern_type", "value", "count"], rows=title_rows)

    description_path = Path(args.description_output)
    description_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(
        description_path,
        fieldnames=["pattern_type", "value", "count"],
        rows=description_rows,
    )

    print("\n=== Segmentation Priority ===")
    print("Primary signals:")
    print("- title_bigrams")
    print("- title_trigrams")
    print("- description_bigrams")
    print("- description_trigrams")
    print("Validation signal:")
    print("- skills")
    print(f"\nSaved skills CSV: {skills_path}")
    print(f"Saved title CSV: {title_path}")
    print(f"Saved description CSV: {description_path}")

    return 0


def normalize_market_patterns_command(args: argparse.Namespace) -> int:
    title_input_path = Path(args.title_input)
    if not title_input_path.exists():
        raise SystemExit(f"Файл не найден: {title_input_path}")

    description_input_path = Path(args.description_input)
    if not description_input_path.exists():
        raise SystemExit(f"Файл не найден: {description_input_path}")

    title_rows = _normalize_pattern_csv(title_input_path)
    description_rows = _normalize_pattern_csv(description_input_path)

    title_output_path = Path(args.title_output)
    title_output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(title_output_path, fieldnames=["pattern_type", "value", "count"], rows=title_rows)

    description_output_path = Path(args.description_output)
    description_output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(
        description_output_path,
        fieldnames=["pattern_type", "value", "count"],
        rows=description_rows,
    )

    print(f"Normalized title rows: {len(title_rows)}")
    print(f"Normalized description rows: {len(description_rows)}")
    print(f"Saved normalized title CSV: {title_output_path}")
    print(f"Saved normalized description CSV: {description_output_path}")
    return 0


def classify_market_patterns_command(args: argparse.Namespace) -> int:
    if args.max_patterns_per_section < 1:
        raise SystemExit("max-patterns-per-section должен быть больше 0.")
    if args.max_job_ids_per_pattern < 0:
        raise SystemExit("max-job-ids-per-pattern не может быть отрицательным.")

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Файл не найден: {input_path}")

    try:
        service = OpenAIService.from_env()
    except OpenAIServiceError as exc:
        raise SystemExit(str(exc)) from exc

    evidence_payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(evidence_payload, dict):
        raise SystemExit("Evidence JSON должен быть объектом.")

    classification_payload = _prepare_pattern_classification_payload(
        evidence_payload,
        max_patterns_per_section=args.max_patterns_per_section,
        max_job_ids_per_pattern=args.max_job_ids_per_pattern,
    )

    try:
        result = service.classify_market_patterns(payload=classification_payload)
    except OpenAIServiceError as exc:
        raise SystemExit(str(exc)) from exc

    output_payload = {
        "source": "openai",
        "model": service.model,
        "input_file": str(input_path),
        "classification_input": classification_payload,
        "result": result,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = result.get("summary", {})
    top_segments = summary.get("top_segment_candidates", [])
    segment_count = len(top_segments) if isinstance(top_segments, list) else 0
    print(f"Classified patterns with model: {service.model}")
    print(f"Patterns per section: {args.max_patterns_per_section}")
    print(f"Top segment candidates: {segment_count}")
    print(f"Saved classification JSON: {output_path}")
    return 0


def build_unique_job_pattern_hits_command(args: argparse.Namespace) -> int:
    if not 0.0 <= args.similarity_threshold <= 1.0:
        raise SystemExit("similarity-threshold должен быть в диапазоне от 0.0 до 1.0.")

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Файл не найден: {input_path}")

    evidence_payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(evidence_payload, dict):
        raise SystemExit("Evidence JSON должен быть объектом.")

    reverse_rows = _build_unique_job_pattern_hits(evidence_payload)
    clusters = _cluster_similar_jobs(reverse_rows, similarity_threshold=args.similarity_threshold)
    output_payload = {
        "source_file": str(input_path),
        "unique_job_count": len(reverse_rows),
        "similarity_threshold": args.similarity_threshold,
        "items": reverse_rows,
        "clusters": clusters,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Unique jobs with pattern hits: {len(reverse_rows)}")
    print(f"Clusters: {len(clusters)}")
    print(f"Similarity threshold: {args.similarity_threshold:.2f}")
    print(f"Saved reverse mapping JSON: {output_path}")
    return 0


def _job_dedupe_key(item: dict[str, object]) -> str:
    uid = str(item.get("uid", "")).strip()
    if uid:
        return uid
    external_link = str(item.get("externalLink", "")).strip()
    if external_link:
        return external_link
    title = str(item.get("title", "")).strip()
    published_at = str(item.get("publishedAt", "")).strip()
    return f"{title}|{published_at}"


def _extract_words(text: str, *, min_length: int) -> list[str]:
    words: list[str] = []
    for raw_word in re.findall(r"[A-Za-z][A-Za-z0-9+.#/&'-]*", text.lower()):
        word = raw_word.strip("'+-./&")
        if len(word) < min_length:
            continue
        if word in STOP_WORDS:
            continue
        words.append(word)
    return words


def _extract_ngrams(words: list[str], size: int) -> list[str]:
    if size < 1 or len(words) < size:
        return []
    return [" ".join(words[index : index + size]) for index in range(len(words) - size + 1)]


def _build_count_rows(
    counts: collections.Counter[str],
    top: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for value, count in counts.most_common(top):
        rows.append({"value": value, "count": count})
    return rows


def _build_pattern_rows(
    *,
    bigrams: collections.Counter[str],
    trigrams: collections.Counter[str],
    top: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for value, count in bigrams.most_common(top):
        rows.append({"pattern_type": "bigram", "value": value, "count": count})
    for value, count in trigrams.most_common(top):
        rows.append({"pattern_type": "trigram", "value": value, "count": count})
    return rows


def _normalize_pattern_csv(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        input_rows = list(csv.DictReader(csv_file))

    aggregated: collections.Counter[tuple[str, str]] = collections.Counter()
    for row in input_rows:
        pattern_type = str(row.get("pattern_type", "")).strip().lower()
        value = str(row.get("value", "")).strip()
        count_raw = row.get("count", 0)
        normalized_value = _normalize_pattern_value(value)
        if not pattern_type or not normalized_value:
            continue
        try:
            count = int(count_raw)
        except (TypeError, ValueError):
            continue
        if count < 1:
            continue
        aggregated[(pattern_type, normalized_value)] += count

    normalized_rows = [
        {"pattern_type": pattern_type, "value": value, "count": count}
        for (pattern_type, value), count in aggregated.items()
    ]
    normalized_rows.sort(key=lambda item: (-int(item["count"]), str(item["pattern_type"]), str(item["value"])))
    return normalized_rows


def _normalize_pattern_value(value: str) -> str:
    normalized = value.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _write_csv(path: Path, *, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _prepare_pattern_classification_payload(
    evidence_payload: dict[str, object],
    *,
    max_patterns_per_section: int = 20,
    max_job_ids_per_pattern: int = 3,
) -> dict[str, list[dict[str, object]]]:
    sections = [
        "title_bigrams",
        "title_trigrams",
        "description_bigrams",
        "description_trigrams",
        "skills",
    ]
    payload: dict[str, list[dict[str, object]]] = {}
    for section in sections:
        rows = evidence_payload.get(section, [])
        normalized_rows: list[dict[str, object]] = []
        if isinstance(rows, list):
            for row in rows[:max_patterns_per_section]:
                if not isinstance(row, dict):
                    continue
                value = str(row.get("value", "")).strip()
                count = int(row.get("count", 0) or 0)
                job_ids_raw = row.get("job_ids", [])
                if not value or count < 1:
                    continue
                job_ids: list[str] = []
                if isinstance(job_ids_raw, list):
                    for job_id in job_ids_raw:
                        job_id_str = str(job_id).strip()
                        if job_id_str:
                            job_ids.append(job_id_str)
                normalized_rows.append(
                    {
                        "value": value,
                        "count": count,
                        "job_ids": job_ids[:max_job_ids_per_pattern],
                    }
                )
        payload[section] = normalized_rows
    return payload


def _build_unique_job_pattern_hits(
    evidence_payload: dict[str, object],
) -> list[dict[str, object]]:
    sections = [
        "title_bigrams",
        "title_trigrams",
        "description_bigrams",
        "description_trigrams",
        "skills",
    ]
    per_job: dict[str, dict[str, object]] = {}

    for section in sections:
        rows = evidence_payload.get(section, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            value = str(row.get("value", "")).strip()
            count = int(row.get("count", 0) or 0)
            job_ids = row.get("job_ids", [])
            if not value or count < 1 or not isinstance(job_ids, list):
                continue
            for job_id_raw in job_ids:
                job_id = str(job_id_raw).strip()
                if not job_id:
                    continue
                item = per_job.setdefault(
                    job_id,
                    {
                        "job_id": job_id,
                        "matched_title_bigrams": [],
                        "matched_title_trigrams": [],
                        "matched_description_bigrams": [],
                        "matched_description_trigrams": [],
                        "matched_skills": [],
                        "total_pattern_hits": 0,
                    },
                )
                key = f"matched_{section}"
                values = item[key]
                if isinstance(values, list) and value not in values:
                    values.append(value)
                    item["total_pattern_hits"] = int(item["total_pattern_hits"]) + 1

    result = list(per_job.values())
    result.sort(key=lambda item: (-int(item["total_pattern_hits"]), str(item["job_id"])))
    return result


def _cluster_similar_jobs(
    rows: list[dict[str, object]],
    *,
    similarity_threshold: float,
) -> list[dict[str, object]]:
    if not rows:
        return []

    clusters: list[dict[str, object]] = []
    assigned: set[str] = set()

    for row in rows:
        job_id = str(row.get("job_id", "")).strip()
        if not job_id or job_id in assigned:
            continue

        member_ids = [job_id]
        assigned.add(job_id)
        for candidate in rows:
            candidate_id = str(candidate.get("job_id", "")).strip()
            if not candidate_id or candidate_id in assigned:
                continue
            score = _job_similarity_score(row, candidate)
            if score >= similarity_threshold:
                member_ids.append(candidate_id)
                assigned.add(candidate_id)

        member_rows = [item for item in rows if str(item.get("job_id", "")).strip() in set(member_ids)]
        representative = member_rows[0]
        clusters.append(
            {
                "cluster_id": f"cluster-{len(clusters) + 1}",
                "size": len(member_ids),
                "job_ids": member_ids,
                "representative_job_id": representative["job_id"],
                "top_shared_title_bigrams": _shared_values(member_rows, "matched_title_bigrams"),
                "top_shared_title_trigrams": _shared_values(member_rows, "matched_title_trigrams"),
                "top_shared_description_bigrams": _shared_values(member_rows, "matched_description_bigrams"),
                "top_shared_description_trigrams": _shared_values(member_rows, "matched_description_trigrams"),
                "top_shared_skills": _shared_values(member_rows, "matched_skills"),
            }
        )

    clusters.sort(key=lambda item: (-int(item["size"]), str(item["cluster_id"])))
    return clusters


def _job_similarity_score(left: dict[str, object], right: dict[str, object]) -> float:
    title_score = _average_overlap(
        left,
        right,
        keys=("matched_title_bigrams", "matched_title_trigrams"),
    )
    description_score = _average_overlap(
        left,
        right,
        keys=("matched_description_bigrams", "matched_description_trigrams"),
    )
    skills_score = _overlap_ratio(
        _as_set(left.get("matched_skills")),
        _as_set(right.get("matched_skills")),
    )
    return (title_score * 0.5) + (description_score * 0.35) + (skills_score * 0.15)


def _average_overlap(
    left: dict[str, object],
    right: dict[str, object],
    *,
    keys: tuple[str, ...],
) -> float:
    scores: list[float] = []
    for key in keys:
        scores.append(_overlap_ratio(_as_set(left.get(key)), _as_set(right.get(key))))
    return sum(scores) / len(scores) if scores else 0.0


def _overlap_ratio(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _as_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    result: set[str] = set()
    for item in value:
        item_str = str(item).strip()
        if item_str:
            result.add(item_str)
    return result


def _shared_values(rows: list[dict[str, object]], key: str, *, top: int = 5) -> list[dict[str, object]]:
    counter: collections.Counter[str] = collections.Counter()
    for row in rows:
        for value in _as_set(row.get(key)):
            counter[value] += 1
    return [{"value": value, "count": count} for value, count in counter.most_common(top)]


if __name__ == "__main__":
    raise SystemExit(main())
