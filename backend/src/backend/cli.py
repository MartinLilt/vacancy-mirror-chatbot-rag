"""CLI for local job-pattern analysis."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from backend.services.assistant.openai import OpenAIProfileNamingService
from backend.services.data.postgres import (
    PostgresJobExportService,
)
from backend.services.integrations.stripe import StripeWebhookService
from backend.services.assistant.infer_server import AssistantInferServer
from backend.services.bot.telegram import TelegramBotService


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vacancy-mirror-chatbot-rag")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pattern_parser = subparsers.add_parser(
        "build-job-pattern-csv",
        help="Build pattern_jobs table from raw_jobs.",
    )
    pattern_parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL connection URL. Default: DB_URL env var",
    )
    pattern_parser.set_defaults(func=build_job_pattern_csv_command)

    normalize_parser = subparsers.add_parser(
        "normalize-job-pattern-csv",
        help="Normalize pattern_jobs to normalized table.",
    )
    normalize_parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL connection URL. Default: DB_URL env var",
    )
    normalize_parser.set_defaults(
        func=normalize_job_pattern_csv_command
    )

    embeddings_parser = subparsers.add_parser(
        "build-job-embeddings",
        help="Build embeddings from normalized jobs.",
    )
    embeddings_parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL connection URL. Default: DB_URL env var",
    )
    embeddings_parser.add_argument(
        "--model",
        default="BAAI/bge-large-en-v1.5",
        help="Local embedding model name.",
    )
    embeddings_parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for embedding generation.",
    )
    embeddings_parser.set_defaults(func=build_job_embeddings_command)

    cluster_parser = subparsers.add_parser(
        "cluster-job-embeddings",
        help="Cluster jobs by cosine similarity over embeddings.",
    )
    cluster_parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL connection URL. Default: DB_URL env var",
    )
    cluster_parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.94,
        help="Cosine similarity threshold for connecting jobs. Default: 0.94",
    )
    cluster_parser.add_argument(
        "--min-cluster-size",
        type=int,
        default=5,
        help="Minimum cluster size to keep. Default: 5",
    )
    cluster_parser.add_argument(
        "--top-clusters",
        type=int,
        default=100,
        help="Maximum number of clusters to save. Default: 100",
    )
    cluster_parser.set_defaults(func=cluster_job_embeddings_command)

    profiles_parser = subparsers.add_parser(
        "build-top-demanded-profiles",
        help="Build top demanded profiles from clusters.",
    )
    profiles_parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL connection URL. Default: DB_URL env var",
    )
    profiles_parser.add_argument(
        "--top-profiles",
        type=int,
        default=0,
        help="Max profiles to save. 0 for all. Default: 0",
    )
    profiles_parser.set_defaults(func=build_top_demanded_profiles_command)

    naming_parser = subparsers.add_parser(
        "name-top-demanded-profiles",
        help="Use OpenAI to name profiles from PostgreSQL.",
    )
    naming_parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL connection URL. Default: DB_URL env var",
    )
    naming_parser.add_argument(
        "--model",
        default="gpt-4-mini",
        help="OpenAI model for naming. Default: gpt-4-mini",
    )
    naming_parser.set_defaults(
        func=name_top_demanded_profiles_command
    )

    core_parser = subparsers.add_parser(
        "build-semantic-core-profiles",
        help="Build semantic core profiles from PostgreSQL.",
    )
    core_parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL connection URL. Default: DB_URL env var",
    )
    core_parser.set_defaults(func=build_semantic_core_profiles_command)

    import_parser = subparsers.add_parser(
        "import-raw-to-db",
        help=(
            "Import a raw Upwork jobs JSON file into PostgreSQL raw_jobs table."
        ),
    )
    import_parser.add_argument(
        "--input",
        default="data/raw/ai_apps_and_integration.json",
        help="Path to raw jobs JSON file.",
    )
    import_parser.add_argument(
        "--category-uid",
        default="",
        help="Upwork category UID to tag rows with.",
    )
    import_parser.add_argument(
        "--category-name",
        default="",
        help="Human-readable category name to tag rows with.",
    )
    import_parser.add_argument(
        "--db-url",
        default="",
        help=(
            "PostgreSQL connection URL. "
            "Falls back to DB_URL environment variable."
        ),
    )
    import_parser.set_defaults(func=import_raw_to_db_command)

    pipeline_parser = subparsers.add_parser(
        "run-full-pipeline",
        help="Run full PostgreSQL-based pipeline.",
    )
    pipeline_parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL connection URL. Default: DB_URL env var",
    )
    pipeline_parser.add_argument(
        "--embedding-model",
        default="BAAI/bge-large-en-v1.5",
        help="Embedding model. Default: BAAI/bge-large-en-v1.5",
    )
    pipeline_parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=32,
        help="Batch size for embeddings. Default: 32",
    )
    pipeline_parser.add_argument(
        "--naming-model",
        default="gpt-4-mini",
        help="OpenAI model for naming. Default: gpt-4-mini",
    )
    pipeline_parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.94,
        help="Similarity threshold for clustering. Default: 0.94",
    )
    pipeline_parser.add_argument(
        "--min-cluster-size",
        type=int,
        default=5,
        help="Minimum cluster size. Default: 5",
    )
    pipeline_parser.add_argument(
        "--top-clusters",
        type=int,
        default=100,
        help="Max clusters to save. Default: 100",
    )
    pipeline_parser.add_argument(
        "--top-profiles",
        type=int,
        default=0,
        help="Max profiles to save. 0 for all. Default: 0",
    )
    pipeline_parser.set_defaults(func=run_full_pipeline_command)

    bot_parser = subparsers.add_parser(
        "telegram-bot",
        help="Start the Telegram bot (long-polling).",
    )
    bot_parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL connection URL. Default: DB_URL env var",
    )
    bot_parser.set_defaults(func=telegram_bot_command)

    webhook_parser = subparsers.add_parser(
        "stripe-webhook",
        help="Start the Stripe webhook HTTP server.",
    )
    webhook_parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL URL. Default: DB_URL env var",
    )
    webhook_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to listen on. Default: WEBHOOK_PORT or 8080",
    )
    webhook_parser.set_defaults(func=stripe_webhook_command)

    infer_parser = subparsers.add_parser(
        "assistant-infer",
        help="Start assistant inference HTTP server for replica scaling.",
    )
    infer_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to listen on. Default: ASSISTANT_INFER_PORT or 8090",
    )
    infer_parser.set_defaults(func=assistant_infer_command)

    return parser


def telegram_bot_command(args: argparse.Namespace) -> int:
    """Start the Telegram bot in long-polling mode."""
    db_url: str | None = args.db_url or None
    bot = TelegramBotService(db_url=db_url)
    bot.run()
    return 0


def stripe_webhook_command(args: argparse.Namespace) -> int:
    """Start the Stripe webhook HTTP server (blocking)."""
    db_url: str | None = args.db_url or None
    port: int | None = args.port or None
    server = StripeWebhookService(db_url=db_url, port=port)
    server.run()
    return 0


def assistant_infer_command(args: argparse.Namespace) -> int:
    """Start assistant inference HTTP server (blocking)."""
    server = AssistantInferServer(port=args.port or None)
    server.run()
    return 0


def import_raw_to_db_command(args: argparse.Namespace) -> int:
    """Load raw Upwork jobs JSON into PostgreSQL raw_jobs table."""
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"File not found: {input_path}")

    items = _load_items(input_path)
    if not items:
        raise SystemExit("No items found in the JSON file.")

    db_url = args.db_url or None  # falls back to DB_URL env var in service
    service = PostgresJobExportService(db_url=db_url)
    service.ensure_table()

    inserted = service.insert_jobs(
        items,
        category_uid=args.category_uid,
        category_name=args.category_name,
    )

    print(f"Jobs in file:    {len(items)}")
    print(f"Newly inserted:  {inserted}")
    print(f"Skipped (dupes): {len(items) - inserted}")
    return 0


def build_job_pattern_csv_command(args: argparse.Namespace) -> int:
    """Build pattern_jobs from raw_jobs in PostgreSQL."""
    service = PostgresJobExportService(db_url=args.db_url or None)
    inserted = service.build_pattern_jobs_from_raw()
    print(f"Pattern jobs built: {inserted} new rows")
    return 0


def normalize_job_pattern_csv_command(
    args: argparse.Namespace,
) -> int:
    """Normalize pattern_jobs and save to pattern_normalized_jobs."""
    service = PostgresJobExportService(db_url=args.db_url or None)
    pattern_jobs = service.get_pattern_jobs()

    normalized_rows = []
    for job in pattern_jobs:
        normalized_rows.append(
            {
                "jobid": job["jobid"],
                "title": _normalize_text(job["title"]),
                "desc": _normalize_text(job.get("desc", "")),
                "skills": _normalize_text(job.get("skills", "")),
                "source_jobid": job["jobid"],
            }
        )

    inserted = service.build_normalized_jobs_from_pattern(
        normalized_rows
    )
    print(f"Normalized jobs: {inserted} new rows")
    return 0


def build_job_embeddings_command(
    args: argparse.Namespace,
) -> int:
    """Build job embeddings from normalized jobs."""
    from backend.services.data.embeddings import (  # noqa: PLC0415
        LocalEmbeddingService,
    )

    db_service = PostgresJobExportService(
        db_url=args.db_url or None
    )
    normalized_jobs = db_service.get_normalized_jobs()

    texts: list[str] = []
    for job in normalized_jobs:
        texts.append(_job_text_for_embedding(job))

    embedding_service = LocalEmbeddingService(
        model_name=args.model
    )
    embeddings = embedding_service.encode(
        texts,
        batch_size=args.batch_size,
    )

    embeddings_data = []
    for job, text, embedding in zip(
        normalized_jobs,
        texts,
        embeddings,
        strict=False,
    ):
        embeddings_data.append(
            {
                "jobid": job["jobid"],
                "text": text,
                "embedding": embedding,
                "source_jobid": job["jobid"],
            }
        )

    inserted = db_service.insert_job_embeddings(
        embeddings_data
    )

    print(f"Job embeddings: {inserted} new rows")
    return 0


def build_job_embeddings_command_old(args: argparse.Namespace) -> int:
    from backend.services.data.embeddings import (  # noqa: PLC0415
        LocalEmbeddingService,
    )
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Файл не найден: {input_path}")

    rows: list[dict[str, str]] = []
    texts: list[str] = []
    with input_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            item = {
                "jobid": str(row.get("jobid", "")).strip(),
                "title": str(row.get("title", "")).strip(),
                "desc": str(row.get("desc", "")).strip(),
                "skills": str(row.get("skills", "")).strip(),
            }
            rows.append(item)
            texts.append(_job_text_for_embedding(item))

    service = LocalEmbeddingService(model_name=args.model)
    embeddings = service.encode(texts, batch_size=args.batch_size)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as out:
        for row, text, embedding in zip(
            rows,
            texts,
            embeddings,
            strict=False,
        ):
            payload = {
                "jobid": row["jobid"],
                "title": row["title"],
                "desc": row["desc"],
                "skills": row["skills"],
                "job_text": text,
                "embedding": embedding,
            }
            out.write(json.dumps(payload, ensure_ascii=False) + "\n")

    print(f"Embeddings exported: {len(rows)}")
    print(f"Saved embeddings JSONL: {output_path}")
    return 0


def cluster_job_embeddings_command(args: argparse.Namespace) -> int:
    """Cluster job embeddings from PostgreSQL."""
    import numpy as np  # noqa: PLC0415
    from sklearn.neighbors import NearestNeighbors  # noqa: PLC0415

    if not 0 <= args.similarity_threshold <= 1:
        raise SystemExit(
            "similarity-threshold должен быть в диапазоне "
            "от 0 до 1."
        )
    if args.min_cluster_size < 1:
        raise SystemExit(
            "min-cluster-size должен быть больше 0."
        )
    if args.top_clusters < 1:
        raise SystemExit(
            "top-clusters должен быть больше 0."
        )

    db_service = PostgresJobExportService(
        db_url=args.db_url or None
    )
    embeddings_data = db_service.get_job_embeddings()
    if not embeddings_data:
        raise SystemExit(
            "Не найдено embeddings для кластеризации."
        )

    items = []
    for row in embeddings_data:
        embedding = row["embedding"]
        if isinstance(embedding, str):
            embedding = json.loads(embedding)
        items.append(
            {
                "jobid": row["jobid"],
                "embedding": np.array(
                    embedding,
                    dtype=np.float32
                ),
            }
        )

    matrix = np.array(
        [item["embedding"] for item in items],
        dtype=np.float32
    )
    radius = 1.0 - args.similarity_threshold
    nn = NearestNeighbors(
        metric="cosine",
        algorithm="brute",
        radius=radius
    )
    nn.fit(matrix)
    graph = nn.radius_neighbors_graph(matrix, mode="distance")

    adjacency: dict[int, set[int]] = defaultdict(set)
    coo = graph.tocoo()
    for left, right, distance in zip(
        coo.row,
        coo.col,
        coo.data,
        strict=False
    ):
        similarity = 1.0 - float(distance)
        if similarity < args.similarity_threshold:
            continue
        adjacency[int(left)].add(int(right))
        adjacency[int(right)].add(int(left))

    for index in range(len(items)):
        adjacency[index].add(index)

    components = _connected_components(adjacency, len(items))

    clusters: list[dict[str, object]] = []
    for cluster_id, component in enumerate(
        components,
        start=1
    ):
        if len(component) < args.min_cluster_size:
            continue
        cluster_jobids = [
            items[index]["jobid"] for index in component
        ]

        centroid = np.mean(
            [items[i]["embedding"] for i in component],
            axis=0
        ).astype(np.float32)
        centroid /= np.linalg.norm(centroid) + 1e-10

        clusters.append(
            {
                "cluster_id": cluster_id,
                "size": len(component),
                "jobids": cluster_jobids,
            }
        )

    clusters.sort(
        key=lambda item: -int(item["size"])
    )
    clusters = clusters[: args.top_clusters]

    inserted = db_service.insert_job_clusters(clusters)

    print(f"Jobs clustered: {len(items)}")
    print(f"Clusters created: {len(clusters)}")
    print(f"New clusters inserted: {inserted}")
    return 0


def build_top_demanded_profiles_command(
    args: argparse.Namespace
) -> int:
    """Build profiles from job clusters in PostgreSQL."""
    db_service = PostgresJobExportService(
        db_url=args.db_url or None
    )
    clusters = db_service.get_job_clusters()
    pattern_jobs = db_service.get_pattern_jobs()

    if not clusters:
        raise SystemExit(
            "Не найдено clusters для построения profiles."
        )

    jobs_by_id = {job["jobid"]: job for job in pattern_jobs}

    profiles: list[dict[str, Any]] = []
    selected_clusters = (
        clusters
        if args.top_profiles == 0
        else clusters[: args.top_profiles]
    )

    for cluster in selected_clusters:
        jobids = cluster.get("jobids", [])
        if not isinstance(jobids, list):
            continue
        cluster_jobs = [
            jobs_by_id[jid]
            for jid in jobids
            if jid in jobs_by_id
        ]
        if not cluster_jobs:
            continue

        size = len(cluster_jobs)
        profiles.append(
            {
                "cluster_id": cluster.get("cluster_id"),
                "role_name": f"Cluster {cluster.get('cluster_id')}",
                "demand_type": "high",
                "demand_ratio": 1.0,
                "total_matching": size,
                "category_uid": "",
                "category_name": "",
            }
        )

    inserted = db_service.insert_profiles(profiles)

    print(f"Profiles built: {len(profiles)}")
    print(f"New profiles inserted: {inserted}")
    return 0


def name_top_demanded_profiles_command(
    args: argparse.Namespace
) -> int:
    """Use OpenAI to name profiles from PostgreSQL."""
    db_service = PostgresJobExportService(
        db_url=args.db_url or None
    )
    profiles = db_service.get_profiles()

    if not profiles:
        raise SystemExit(
            "Не найдено profiles для naming."
        )

    naming_input: list[dict[str, object]] = []
    for profile in profiles:
        naming_input.append(
            {
                "cluster_id": profile.get("cluster_id"),
                "current_role_name": (
                    profile.get("role_name")
                ),
                "size": profile.get("size"),
            }
        )

    service = OpenAIProfileNamingService(model=args.model)
    naming_result = service.name_profiles(
        profiles=naming_input
    )
    llm_profiles = naming_result.get("profiles", [])
    if not isinstance(llm_profiles, list):
        raise SystemExit(
            "LLM naming response invalid."
        )

    llm_by_cluster_id = {
        str(item.get("cluster_id")): item
        for item in llm_profiles
        if isinstance(item, dict)
        and item.get("cluster_id") is not None
    }

    updated_profiles = []
    for profile in profiles:
        cluster_id = str(profile.get("cluster_id"))
        llm_item = llm_by_cluster_id.get(cluster_id, {})
        updated_profiles.append(
            {
                "id": profile.get("id"),
                "cluster_id": profile.get("cluster_id"),
                "role_name": llm_item.get(
                    "role_name",
                    profile.get("role_name")
                ),
                "demand_type": profile.get("demand_type"),
                "demand_ratio": profile.get("demand_ratio"),
                "total_matching": (
                    profile.get("total_matching")
                ),
                "semantic_core": (
                    profile.get("semantic_core")
                ),
            }
        )

    print(f"Profiles named: {len(updated_profiles)}")
    return 0


def build_semantic_core_profiles_command(
    args: argparse.Namespace
) -> int:
    """Build semantic core profiles from PostgreSQL."""
    db_service = PostgresJobExportService(
        db_url=args.db_url or None
    )
    profiles = db_service.get_profiles()
    pattern_jobs = db_service.get_pattern_jobs()

    if not profiles:
        raise SystemExit(
            "Не найдено profiles для semantic core."
        )

    jobs_by_id = {job["jobid"]: job for job in pattern_jobs}

    for profile in profiles:
        job_ids = profile.get("job_ids", [])
        if not isinstance(job_ids, list):
            continue
        jobs = [
            jobs_by_id[jid]
            for jid in job_ids
            if jid in jobs_by_id
        ]
        if not jobs:
            continue

        semantic_core = json.dumps(
            {
                "size": len(jobs),
                "sample_titles": [
                    job["title"]
                    for job in jobs[:5]
                ],
            },
            ensure_ascii=False,
        )

        profile["semantic_core"] = semantic_core

    print(f"Semantic cores built: {len(profiles)}")
    return 0


def run_full_pipeline_command(
    args: argparse.Namespace
) -> int:
    """Run full PostgreSQL-based pipeline."""
    db_url = args.db_url or None
    db_service = PostgresJobExportService(db_url=db_url)

    print("🚀 Running full pipeline...")

    print("1️⃣  Building pattern jobs...")
    db_service.build_pattern_jobs_from_raw()

    print("2️⃣  Normalizing pattern jobs...")
    pattern_jobs = db_service.get_pattern_jobs()
    normalized_rows = []
    for job in pattern_jobs:
        normalized_rows.append(
            {
                "jobid": job["jobid"],
                "title": _normalize_text(job["title"]),
                "desc": _normalize_text(job.get("desc", "")),
                "skills": _normalize_text(
                    job.get("skills", "")
                ),
                "source_jobid": job["jobid"],
            }
        )
    db_service.build_normalized_jobs_from_pattern(
        normalized_rows
    )

    print("3️⃣  Building embeddings...")
    build_job_embeddings_command(
        argparse.Namespace(
            db_url=db_url,
            model=args.embedding_model,
            batch_size=args.embedding_batch_size,
        )
    )

    print("4️⃣  Clustering embeddings...")
    cluster_job_embeddings_command(
        argparse.Namespace(
            db_url=db_url,
            similarity_threshold=args.similarity_threshold,
            min_cluster_size=args.min_cluster_size,
            top_clusters=args.top_clusters,
        )
    )

    print("5️⃣  Building profiles...")
    build_top_demanded_profiles_command(
        argparse.Namespace(
            db_url=db_url,
            top_profiles=args.top_profiles,
        )
    )

    print("6️⃣  Naming profiles...")
    name_top_demanded_profiles_command(
        argparse.Namespace(
            db_url=db_url,
            model=args.naming_model,
        )
    )

    print("7️⃣  Building semantic cores...")
    build_semantic_core_profiles_command(
        argparse.Namespace(
            db_url=db_url,
        )
    )

    print("✅ Full pipeline completed!")
    return 0


def _demand_type(ratio: float) -> str:
    """Classify market demand based on total_matching / size ratio.

    - broad:  ratio > 5  — wide market, diverse job postings.
    - niche:  ratio 1.5–5 — focused market, similar postings.
    - exotic: ratio < 1.5 — rare or very specific topic.
    """
    if ratio > 5.0:
        return "broad"
    if ratio >= 1.5:
        return "niche"
    return "exotic"


def _connected_components(adjacency: dict[int, set[int]], total_nodes: int) -> list[list[int]]:
    visited: set[int] = set()
    components: list[list[int]] = []

    for node in range(total_nodes):
        if node in visited:
            continue
        queue: deque[int] = deque([node])
        visited.add(node)
        component: list[int] = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in adjacency.get(current, {current}):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append(neighbor)
        components.append(component)
    return components


def _collect_ngram_patterns(values: list[str], *, top_per_size: int) -> dict[str, list[dict[str, object]]]:
    patterns: dict[str, list[dict[str, object]]] = {}
    for n in range(1, 5):
        counter: Counter[str] = Counter()
        for value in values:
            tokens = _ngram_tokens(value)
            if len(tokens) < n:
                continue
            for index in range(len(tokens) - n + 1):
                phrase = " ".join(tokens[index:index + n])
                counter[phrase] += 1
        patterns[f"{n}_gram"] = [
            {"phrase": phrase, "count": count}
            for phrase, count in counter.most_common(top_per_size)
        ]
    return patterns


def _ngram_tokens(value: str) -> list[str]:
    cleaned = _normalize_text(value)
    return [token for token in cleaned.split() if token]


def _top_terms(values: list[str], *, top_n: int) -> list[dict[str, object]]:
    counter: Counter[str] = Counter()
    for value in values:
        for token in _tokenize_text(value):
            counter[token] += 1
    return [{"term": term, "count": count} for term, count in counter.most_common(top_n)]


def _top_skill_phrases(values: list[str], *, top_n: int) -> list[dict[str, object]]:
    counter: Counter[str] = Counter()
    for value in values:
        for part in value.split("|"):
            normalized = _normalize_text(part)
            if not normalized:
                continue
            counter[normalized] += 1
    return [{"skill": skill, "count": count} for skill, count in counter.most_common(top_n)]


def _role_label_from_terms(terms: list[dict[str, object]]) -> str:
    selected: list[str] = []
    for item in terms:
        term = str(item.get("term", "")).strip()
        if not term or term in _ROLE_LABEL_STOPWORDS:
            continue
        selected.append(term)
        if len(selected) == 3:
            break
    if not selected:
        return "Generic Web Development"
    if len(selected) == 1:
        return f"{selected[0].capitalize()} Specialist"
    return " ".join(word.capitalize() for word in selected)


def _tokenize_text(value: str) -> list[str]:
    cleaned = _normalize_text(value)
    return [token for token in cleaned.split() if len(token) >= 3 and token not in _TOKEN_STOPWORDS]


_TOKEN_STOPWORDS = {
    "and", "for", "the", "with", "that", "this", "from", "you", "your", "are", "our", "but",
    "not", "will", "can", "need", "needed", "want", "looking", "look", "project", "projects",
    "experience", "experienced", "strong", "should", "must", "please", "include", "candidate",
    "ideal", "work", "working", "build", "developer", "developers", "development", "web",
    "exciting", "innovative", "ongoing", "creative", "premium", "specializing", "agency", "agencies",
    "required", "seeking", "quick", "new", "modern", "small", "custom", "overview", "role",
}


_ROLE_LABEL_STOPWORDS = _TOKEN_STOPWORDS | {
    "application", "applications", "website", "websites", "site", "sites", "page", "pages",
    "expert", "experts", "maintenance", "improvement", "upgrade", "updates"
}


def _load_jobs_csv_by_id(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            jobid = str(row.get("jobid", "")).strip()
            if not jobid:
                continue
            rows[jobid] = {
                "jobid": jobid,
                "title": str(row.get("title", "")).strip(),
                "desc": str(row.get("desc", "")).strip(),
                "skills": str(row.get("skills", "")).strip(),
            }
    return rows


def _load_embedding_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            embedding = item.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                continue
            rows.append(
                {
                    "jobid": str(item.get("jobid", "")).strip(),
                    "title": str(item.get("title", "")).strip(),
                    "desc": str(item.get("desc", "")).strip(),
                    "skills": str(item.get("skills", "")).strip(),
                    "embedding": embedding,
                }
            )
    return rows


def _job_text_for_embedding(row: dict[str, str]) -> str:
    return "\n".join(
        [
            f"title: {row['title']}",
            f"skills: {row['skills']}",
            f"description: {row['desc']}",
        ]
    ).strip()


def _load_items(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"Файл не найден: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("items", [])
    else:
        raise SystemExit(
            "JSON должен быть либо списком вакансий, либо объектом с полем items.")

    if not isinstance(items, list):
        raise SystemExit("В JSON нет корректного списка items.")
    return items


def _job_identifier(item: dict) -> str:
    for key in ("uid", "id", "jobId", "ciphertext"):
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    for key in ("url", "link", "jobUrl"):
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    title = str(item.get("title", "")).strip() or "untitled"
    return f"title:{title}"


def _string_field(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def _skills_field(value: object) -> str:
    if not isinstance(value, list):
        return ""
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return " | ".join(cleaned)


def _extract_skills(item: dict) -> str:
    """Extract skills from a job dict.

    Supports two formats:
    - ``skills``: list of plain strings (old web_development_jobs format).
    - ``attrs``: list of dicts with ``prefLabel`` key (new scraper format).
    """
    skills_raw = item.get("skills")
    if isinstance(skills_raw, list) and skills_raw:
        return _skills_field(skills_raw)

    attrs = item.get("attrs")
    if isinstance(attrs, list):
        labels = [
            str(a.get("prefLabel", "")).strip()
            for a in attrs
            if isinstance(a, dict) and a.get("prefLabel")
        ]
        return " | ".join(labels)

    return ""


def _normalize_text(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _cleanup_legacy_pattern_files(*, output_dir: Path, keep: Path) -> None:
    for path in output_dir.glob("*.csv"):
        if path == keep:
            continue
        path.unlink(missing_ok=True)


def _write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
