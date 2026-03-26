"""CLI for local job-pattern analysis."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np
from sklearn.neighbors import NearestNeighbors

from vacancy_mirror_chatbot_rag.services.embeddings import LocalEmbeddingService
from vacancy_mirror_chatbot_rag.services.openai import OpenAIProfileNamingService


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vacancy-mirror-chatbot-rag")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pattern_parser = subparsers.add_parser(
        "build-job-pattern-csv",
        help="Read local job corpus and build one flat CSV with jobid, title, desc, and skills.",
    )
    pattern_parser.add_argument(
        "--input",
        default="data/raw/ai_apps_and_integration.json",
        help="Path to source JSON file.",
    )
    pattern_parser.add_argument(
        "--output-dir",
        default="data/pattern_jobs",
        help="Output directory for generated CSV file. Default: data/pattern_jobs",
    )
    pattern_parser.add_argument(
        "--output-name",
        default="jobs.csv",
        help="Output CSV file name. Default: jobs.csv",
    )
    pattern_parser.set_defaults(func=build_job_pattern_csv_command)

    normalize_parser = subparsers.add_parser(
        "normalize-job-pattern-csv",
        help="Normalize jobs.csv for embedding preparation into lowercase ASCII-like text without special symbols.",
    )
    normalize_parser.add_argument(
        "--input",
        default="data/pattern_jobs/jobs.csv",
        help="Path to source jobs CSV file. Default: data/pattern_jobs/jobs.csv",
    )
    normalize_parser.add_argument(
        "--output-dir",
        default="data/pattern_normalized_jobs",
        help="Output directory for normalized CSV file. Default: data/pattern_normalized_jobs",
    )
    normalize_parser.add_argument(
        "--output-name",
        default="jobs.csv",
        help="Output CSV file name. Default: jobs.csv",
    )
    normalize_parser.set_defaults(func=normalize_job_pattern_csv_command)

    embeddings_parser = subparsers.add_parser(
        "build-job-embeddings",
        help="Build local embeddings from normalized jobs CSV using BAAI/bge-small-en-v1.5.",
    )
    embeddings_parser.add_argument(
        "--input",
        default="data/pattern_normalized_jobs/jobs.csv",
        help="Path to normalized jobs CSV file. Default: data/pattern_normalized_jobs/jobs.csv",
    )
    embeddings_parser.add_argument(
        "--output",
        default="data/job_embeddings.jsonl",
        help="Output JSONL path for job embeddings. Default: data/job_embeddings.jsonl",
    )
    embeddings_parser.add_argument(
        "--model",
        default="BAAI/bge-small-en-v1.5",
        help="Local embedding model name. Default: BAAI/bge-small-en-v1.5",
    )
    embeddings_parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for local embedding generation. Default: 32",
    )
    embeddings_parser.set_defaults(func=build_job_embeddings_command)

    cluster_parser = subparsers.add_parser(
        "cluster-job-embeddings",
        help="Cluster jobs by cosine similarity over local embeddings.",
    )
    cluster_parser.add_argument(
        "--input",
        default="data/job_embeddings.jsonl",
        help="Path to embeddings JSONL file. Default: data/job_embeddings.jsonl",
    )
    cluster_parser.add_argument(
        "--output",
        default="data/job_clusters.json",
        help="Output JSON path for clusters. Default: data/job_clusters.json",
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
        help="Build top demanded role profiles and semantic cores from clustered jobs.",
    )
    profiles_parser.add_argument(
        "--clusters-input",
        default="data/job_clusters.json",
        help="Path to clusters JSON file. Default: data/job_clusters.json",
    )
    profiles_parser.add_argument(
        "--jobs-input",
        default="data/pattern_jobs/jobs.csv",
        help="Path to source jobs CSV file. Default: data/pattern_jobs/jobs.csv",
    )
    profiles_parser.add_argument(
        "--output",
        default="data/top_demanded_profiles.json",
        help="Output JSON path for top demanded profiles. Default: data/top_demanded_profiles.json",
    )
    profiles_parser.add_argument(
        "--top-profiles",
        type=int,
        default=0,
        help="Maximum number of role profiles to save. Use 0 for all. Default: 0",
    )
    profiles_parser.set_defaults(func=build_top_demanded_profiles_command)

    naming_parser = subparsers.add_parser(
        "name-top-demanded-profiles",
        help="Use OpenAI to assign human-readable names to top demanded role profiles.",
    )
    naming_parser.add_argument(
        "--input",
        default="data/top_demanded_profiles.json",
        help="Path to top demanded profiles JSON. Default: data/top_demanded_profiles.json",
    )
    naming_parser.add_argument(
        "--output",
        default="data/top_demanded_profiles_named.json",
        help="Output JSON path for named profiles. Default: data/top_demanded_profiles_named.json",
    )
    naming_parser.add_argument(
        "--model",
        default="gpt-4.1-mini",
        help="OpenAI model for naming. Default: gpt-4.1-mini",
    )
    naming_parser.set_defaults(func=name_top_demanded_profiles_command)

    core_parser = subparsers.add_parser(
        "build-semantic-core-profiles",
        help="Expand named profiles into semantic cores with real jobs and frequent title/description phrases.",
    )
    core_parser.add_argument(
        "--profiles-input",
        default="data/top_demanded_profiles_named.json",
        help="Path to named profiles JSON. Default: data/top_demanded_profiles_named.json",
    )
    core_parser.add_argument(
        "--jobs-input",
        default="data/pattern_jobs/jobs.csv",
        help="Path to source jobs CSV file. Default: data/pattern_jobs/jobs.csv",
    )
    core_parser.add_argument(
        "--output",
        default="data/top_demanded_profiles_semantic_core.json",
        help="Output JSON path for semantic cores. Default: data/top_demanded_profiles_semantic_core.json",
    )
    core_parser.add_argument(
        "--top-phrases-per-size",
        type=int,
        default=15,
        help="Top phrases to keep for each n-gram size. Default: 15",
    )
    core_parser.set_defaults(func=build_semantic_core_profiles_command)

    pipeline_parser = subparsers.add_parser(
        "run-full-pipeline",
        help="Run the full vacancy-mirror pipeline from raw jobs JSON to semantic core profiles.",
    )
    pipeline_parser.add_argument(
        "--raw-input",
        default="data/raw/ai_apps_and_integration.json",
        help="Path to raw jobs JSON.",
    )
    pipeline_parser.add_argument(
        "--pattern-output-dir",
        default="data/pattern_jobs",
        help="Output directory for flat jobs CSV. Default: data/pattern_jobs",
    )
    pipeline_parser.add_argument(
        "--normalized-output-dir",
        default="data/pattern_normalized_jobs",
        help="Output directory for normalized jobs CSV. Default: data/pattern_normalized_jobs",
    )
    pipeline_parser.add_argument(
        "--embeddings-output",
        default="data/job_embeddings.jsonl",
        help="Output JSONL path for embeddings. Default: data/job_embeddings.jsonl",
    )
    pipeline_parser.add_argument(
        "--clusters-output",
        default="data/job_clusters.json",
        help="Output JSON path for clusters. Default: data/job_clusters.json",
    )
    pipeline_parser.add_argument(
        "--profiles-output",
        default="data/top_demanded_profiles.json",
        help="Output JSON path for auto-labeled profiles. Default: data/top_demanded_profiles.json",
    )
    pipeline_parser.add_argument(
        "--named-profiles-output",
        default="data/top_demanded_profiles_named.json",
        help="Output JSON path for OpenAI-named profiles. Default: data/top_demanded_profiles_named.json",
    )
    pipeline_parser.add_argument(
        "--semantic-core-output",
        default="data/top_demanded_profiles_semantic_core.json",
        help="Output JSON path for semantic cores. Default: data/top_demanded_profiles_semantic_core.json",
    )
    pipeline_parser.add_argument(
        "--embedding-model",
        default="BAAI/bge-small-en-v1.5",
        help="Local embedding model name. Default: BAAI/bge-small-en-v1.5",
    )
    pipeline_parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=32,
        help="Batch size for local embedding generation. Default: 32",
    )
    pipeline_parser.add_argument(
        "--naming-model",
        default="gpt-4.1-mini",
        help="OpenAI model for naming role profiles. Default: gpt-4.1-mini",
    )
    pipeline_parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.94,
        help="Cosine similarity threshold for clustering. Default: 0.94",
    )
    pipeline_parser.add_argument(
        "--min-cluster-size",
        type=int,
        default=5,
        help="Minimum cluster size to keep. Default: 5",
    )
    pipeline_parser.add_argument(
        "--top-clusters",
        type=int,
        default=100,
        help="Maximum number of clusters to save. Default: 100",
    )
    pipeline_parser.add_argument(
        "--top-profiles",
        type=int,
        default=0,
        help="Maximum number of role profiles to save. Use 0 for all. Default: 0",
    )
    pipeline_parser.add_argument(
        "--top-phrases-per-size",
        type=int,
        default=15,
        help="Top phrases to keep for each n-gram size in semantic core output. Default: 15",
    )
    pipeline_parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild all steps even if the target artifact already exists.",
    )
    pipeline_parser.set_defaults(func=run_full_pipeline_command)

    return parser


def build_job_pattern_csv_command(args: argparse.Namespace) -> int:
    items = _load_items(Path(args.input))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / args.output_name

    rows: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "jobid": _job_identifier(item),
                "title": _string_field(item.get("title")),
                "desc": _string_field(item.get("description")),
                "skills": _extract_skills(item),
            }
        )

    _write_csv(output_path, ["jobid", "title", "desc", "skills"], rows)
    _cleanup_legacy_pattern_files(output_dir=output_dir, keep=output_path)

    print(f"Jobs exported: {len(rows)}")
    print(f"Saved CSV: {output_path}")
    return 0


def normalize_job_pattern_csv_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Файл не найден: {input_path}")

    rows: list[dict[str, str]] = []
    with input_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            rows.append(
                {
                    "jobid": str(row.get("jobid", "")).strip(),
                    "title": _normalize_text(str(row.get("title", ""))),
                    "desc": _normalize_text(str(row.get("desc", ""))),
                    "skills": _normalize_text(str(row.get("skills", ""))),
                }
            )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / args.output_name
    _write_csv(output_path, ["jobid", "title", "desc", "skills"], rows)

    print(f"Normalized jobs exported: {len(rows)}")
    print(f"Saved normalized CSV: {output_path}")
    return 0


def build_job_embeddings_command(args: argparse.Namespace) -> int:
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
        for row, text, embedding in zip(rows, texts, embeddings, strict=False):
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
    if not 0 <= args.similarity_threshold <= 1:
        raise SystemExit(
            "similarity-threshold должен быть в диапазоне от 0 до 1.")
    if args.min_cluster_size < 1:
        raise SystemExit("min-cluster-size должен быть больше 0.")
    if args.top_clusters < 1:
        raise SystemExit("top-clusters должен быть больше 0.")

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Файл не найден: {input_path}")

    items = _load_embedding_rows(input_path)
    if not items:
        raise SystemExit("Не найдено embeddings для кластеризации.")

    matrix = np.array([item["embedding"] for item in items], dtype=np.float32)
    radius = 1.0 - args.similarity_threshold
    nn = NearestNeighbors(metric="cosine", algorithm="brute", radius=radius)
    nn.fit(matrix)
    graph = nn.radius_neighbors_graph(matrix, mode="distance")

    adjacency: dict[int, set[int]] = defaultdict(set)
    coo = graph.tocoo()
    for left, right, distance in zip(coo.row, coo.col, coo.data, strict=False):
        similarity = 1.0 - float(distance)
        if similarity < args.similarity_threshold:
            continue
        adjacency[int(left)].add(int(right))
        adjacency[int(right)].add(int(left))

    for index in range(len(items)):
        adjacency[index].add(index)

    components = _connected_components(adjacency, len(items))

    # Soft threshold for counting all matching jobs per cluster centroid.
    # Uses a wider radius so we capture jobs that are semantically related
    # but not identical enough to be in the core cluster.
    soft_threshold = max(0.0, args.similarity_threshold - 0.10)

    clusters: list[dict[str, object]] = []
    for cluster_id, component in enumerate(components, start=1):
        if len(component) < args.min_cluster_size:
            continue
        cluster_items = [items[index] for index in component]

        # Compute centroid as mean of normalised embeddings.
        centroid = np.mean(
            [items[i]["embedding"] for i in component], axis=0
        ).astype(np.float32)
        centroid /= np.linalg.norm(centroid) + 1e-10

        # Count ALL corpus jobs whose cosine similarity to centroid
        # exceeds soft_threshold — this is the real market demand size.
        sims = matrix @ centroid  # cosine similarity (embeddings normalised)
        matching_indices = [
            int(idx)
            for idx, sim in enumerate(sims)
            if float(sim) >= soft_threshold
        ]

        top_title_terms = _top_terms(
            [item["title"] for item in cluster_items], top_n=10
        )
        top_skill_terms = _top_terms(
            [item["skills"] for item in cluster_items], top_n=10
        )
        clusters.append(
            {
                "cluster_id": cluster_id,
                "size": len(component),
                "total_matching": len(matching_indices),
                "job_ids": [item["jobid"] for item in cluster_items],
                "all_matching_job_ids": [
                    items[i]["jobid"] for i in matching_indices
                ],
                "sample_titles": [
                    item["title"] for item in cluster_items[:5]
                ],
                "top_title_terms": top_title_terms,
                "top_skill_terms": top_skill_terms,
            }
        )

    clusters.sort(
        key=lambda item: (
            -int(item["total_matching"]), int(item["cluster_id"])
        )
    )
    clusters = clusters[: args.top_clusters]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "similarity_threshold": args.similarity_threshold,
                "min_cluster_size": args.min_cluster_size,
                "total_jobs": len(items),
                "cluster_count": len(clusters),
                "clusters": clusters,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Jobs clustered: {len(items)}")
    print(f"Clusters saved: {len(clusters)}")
    print(f"Saved clusters JSON: {output_path}")
    return 0


def build_top_demanded_profiles_command(args: argparse.Namespace) -> int:
    clusters_path = Path(args.clusters_input)
    jobs_path = Path(args.jobs_input)
    if not clusters_path.exists():
        raise SystemExit(f"Файл не найден: {clusters_path}")
    if not jobs_path.exists():
        raise SystemExit(f"Файл не найден: {jobs_path}")
    if args.top_profiles < 0:
        raise SystemExit("top-profiles должен быть 0 или больше.")

    clusters_payload = json.loads(clusters_path.read_text(encoding="utf-8"))
    raw_clusters = clusters_payload.get("clusters", [])
    if not isinstance(raw_clusters, list):
        raise SystemExit("В clusters JSON нет корректного списка clusters.")

    jobs_by_id = _load_jobs_csv_by_id(jobs_path)

    profiles: list[dict[str, object]] = []
    selected_clusters = raw_clusters if args.top_profiles == 0 else raw_clusters[
        : args.top_profiles]
    for cluster in selected_clusters:
        job_ids = cluster.get("job_ids", [])
        if not isinstance(job_ids, list):
            continue
        cluster_jobs = [jobs_by_id[job_id]
                        for job_id in job_ids if job_id in jobs_by_id]
        if not cluster_jobs:
            continue

        top_title_terms = _top_terms([job["title"]
                                     for job in cluster_jobs], top_n=15)
        top_description_terms = _top_terms(
            [job["desc"] for job in cluster_jobs], top_n=15)
        top_skill_phrases = _top_skill_phrases(
            [job["skills"] for job in cluster_jobs], top_n=15)

        size = len(cluster_jobs)
        total_matching = int(
            cluster.get("total_matching", size)
        )
        demand_ratio = round(total_matching / size, 2) if size else 0.0
        profiles.append(
            {
                "cluster_id": cluster.get("cluster_id"),
                "role_name": _role_label_from_terms(top_title_terms),
                "size": size,
                "total_matching": total_matching,
                "demand_ratio": demand_ratio,
                "demand_type": _demand_type(demand_ratio),
                "job_ids": [job["jobid"] for job in cluster_jobs],
                "sample_titles": [job["title"] for job in cluster_jobs[:10]],
                "top_title_terms": top_title_terms,
                "top_description_terms": top_description_terms,
                "top_skill_phrases": top_skill_phrases,
            }
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "source_clusters_file": str(clusters_path),
                "source_jobs_file": str(jobs_path),
                "profile_count": len(profiles),
                "profiles": profiles,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Profiles built: {len(profiles)}")
    print(f"Saved top profiles JSON: {output_path}")
    return 0


def name_top_demanded_profiles_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Файл не найден: {input_path}")

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    profiles = payload.get("profiles", [])
    if not isinstance(profiles, list) or not profiles:
        raise SystemExit(
            "В top demanded profiles JSON нет корректного списка profiles.")

    naming_input: list[dict[str, object]] = []
    for profile in profiles:
        naming_input.append(
            {
                "cluster_id": profile.get("cluster_id"),
                "current_role_name": profile.get("role_name"),
                "size": profile.get("size"),
                "sample_titles": profile.get("sample_titles", [])[:5],
                "top_title_terms": profile.get("top_title_terms", [])[:10],
                "top_skill_phrases": profile.get("top_skill_phrases", [])[:10],
            }
        )

    service = OpenAIProfileNamingService(model=args.model)
    naming_result = service.name_profiles(profiles=naming_input)
    llm_profiles = naming_result.get("profiles", [])
    if not isinstance(llm_profiles, list):
        raise SystemExit(
            "LLM naming response does not contain a valid profiles list.")

    llm_by_cluster_id = {
        str(item.get("cluster_id")): item
        for item in llm_profiles
        if isinstance(item, dict) and item.get("cluster_id") is not None
    }

    named_profiles: list[dict[str, object]] = []
    for profile in profiles:
        cluster_id = str(profile.get("cluster_id"))
        llm_item = llm_by_cluster_id.get(cluster_id, {})
        named_profile = dict(profile)
        named_profile["auto_role_name"] = profile.get("role_name")
        named_profile["role_name"] = llm_item.get(
            "role_name", profile.get("role_name"))
        named_profile["role_name_reason"] = llm_item.get("reason", "")
        named_profiles.append(named_profile)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "source_profiles_file": str(input_path),
                "model": args.model,
                "profile_count": len(named_profiles),
                "profiles": named_profiles,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Profiles named: {len(named_profiles)}")
    print(f"Saved named profiles JSON: {output_path}")
    return 0


def build_semantic_core_profiles_command(args: argparse.Namespace) -> int:
    profiles_path = Path(args.profiles_input)
    jobs_path = Path(args.jobs_input)
    if not profiles_path.exists():
        raise SystemExit(f"Файл не найден: {profiles_path}")
    if not jobs_path.exists():
        raise SystemExit(f"Файл не найден: {jobs_path}")
    if args.top_phrases_per_size < 1:
        raise SystemExit("top-phrases-per-size должен быть больше 0.")

    payload = json.loads(profiles_path.read_text(encoding="utf-8"))
    profiles = payload.get("profiles", [])
    if not isinstance(profiles, list) or not profiles:
        raise SystemExit(
            "В named profiles JSON нет корректного списка profiles.")

    jobs_by_id = _load_jobs_csv_by_id(jobs_path)
    semantic_profiles: list[dict[str, object]] = []

    for profile in profiles:
        job_ids = profile.get("job_ids", [])
        if not isinstance(job_ids, list):
            continue
        jobs = [jobs_by_id[job_id]
                for job_id in job_ids if job_id in jobs_by_id]
        if not jobs:
            continue

        semantic_profiles.append(
            {
                "cluster_id": profile.get("cluster_id"),
                "role_name": profile.get("role_name"),
                "auto_role_name": profile.get("auto_role_name", ""),
                "role_name_reason": profile.get("role_name_reason", ""),
                "size": len(jobs),
                "title_patterns": _collect_ngram_patterns(
                    [job["title"] for job in jobs], top_per_size=args.top_phrases_per_size
                ),
                "description_patterns": _collect_ngram_patterns(
                    [job["desc"] for job in jobs], top_per_size=args.top_phrases_per_size
                ),
                "skills": _top_skill_phrases([job["skills"] for job in jobs], top_n=50),
                "jobs": [
                    {
                        "jobid": job["jobid"],
                        "title": job["title"],
                        "desc": job["desc"],
                        "skills": job["skills"],
                    }
                    for job in jobs
                ],
            }
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "source_profiles_file": str(profiles_path),
                "source_jobs_file": str(jobs_path),
                "profile_count": len(semantic_profiles),
                "profiles": semantic_profiles,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Semantic cores built: {len(semantic_profiles)}")
    print(f"Saved semantic core JSON: {output_path}")
    return 0


def run_full_pipeline_command(args: argparse.Namespace) -> int:
    pattern_csv_path = Path(args.pattern_output_dir) / "jobs.csv"
    normalized_csv_path = Path(args.normalized_output_dir) / "jobs.csv"

    steps: list[tuple[str, object, argparse.Namespace, Path]] = [
        (
            "build-job-pattern-csv",
            build_job_pattern_csv_command,
            argparse.Namespace(
                input=args.raw_input,
                output_dir=args.pattern_output_dir,
                output_name="jobs.csv",
            ),
            pattern_csv_path,
        ),
        (
            "normalize-job-pattern-csv",
            normalize_job_pattern_csv_command,
            argparse.Namespace(
                input=str(pattern_csv_path),
                output_dir=args.normalized_output_dir,
                output_name="jobs.csv",
            ),
            normalized_csv_path,
        ),
        (
            "build-job-embeddings",
            build_job_embeddings_command,
            argparse.Namespace(
                input=str(normalized_csv_path),
                output=args.embeddings_output,
                model=args.embedding_model,
                batch_size=args.embedding_batch_size,
            ),
            Path(args.embeddings_output),
        ),
        (
            "cluster-job-embeddings",
            cluster_job_embeddings_command,
            argparse.Namespace(
                input=args.embeddings_output,
                output=args.clusters_output,
                similarity_threshold=args.similarity_threshold,
                min_cluster_size=args.min_cluster_size,
                top_clusters=args.top_clusters,
            ),
            Path(args.clusters_output),
        ),
        (
            "build-top-demanded-profiles",
            build_top_demanded_profiles_command,
            argparse.Namespace(
                clusters_input=args.clusters_output,
                jobs_input=str(pattern_csv_path),
                output=args.profiles_output,
                top_profiles=args.top_profiles,
            ),
            Path(args.profiles_output),
        ),
        (
            "name-top-demanded-profiles",
            name_top_demanded_profiles_command,
            argparse.Namespace(
                input=args.profiles_output,
                output=args.named_profiles_output,
                model=args.naming_model,
            ),
            Path(args.named_profiles_output),
        ),
        (
            "build-semantic-core-profiles",
            build_semantic_core_profiles_command,
            argparse.Namespace(
                profiles_input=args.named_profiles_output,
                jobs_input=str(pattern_csv_path),
                output=args.semantic_core_output,
                top_phrases_per_size=args.top_phrases_per_size,
            ),
            Path(args.semantic_core_output),
        ),
    ]

    print("Running full pipeline...")
    for step_name, handler, step_args, target_path in steps:
        if target_path.exists() and not args.force:
            print(
                f"[pipeline] {step_name} -> skip ({target_path} already exists)")
            continue
        print(f"[pipeline] {step_name}")
        handler(step_args)

    print("Full pipeline completed.")
    print(f"Final semantic core JSON: {args.semantic_core_output}")
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
