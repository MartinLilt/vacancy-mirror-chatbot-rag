#!/usr/bin/env python
"""Quick test of embedding generation with bge-large."""

from __future__ import annotations

import os
import psycopg2
from vacancy_mirror_chatbot_rag.services.embeddings import (
    LocalEmbeddingService,
)
from vacancy_mirror_chatbot_rag.services.postgres import (
    PostgresJobExportService,
)


def main() -> None:
    """Test embeddings on 5 sample jobs."""
    db_url = (
        os.environ.get("DB_URL")
        or "postgresql://app:test_password_12345@localhost:5432/"
        "vacancy_mirror"
    )

    # Load sample jobs
    print("📊 Loading 5 sample normalized jobs...")
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT jobid, title, "desc", skills
            FROM pattern_normalized_jobs
            LIMIT 5
        """)
        jobs = cur.fetchall()
    conn.close()

    print(f"✅ Loaded {len(jobs)} jobs")

    # Build text for embedding
    texts = [
        f"title: {job[1]}\nskills: {job[3]}\n"
        f"description: {job[2]}"
        for job in jobs
    ]

    # Load embedding model
    print("🔄 Loading BAAI/bge-large-en-v1.5...")
    service = LocalEmbeddingService(
        model_name="BAAI/bge-large-en-v1.5"
    )

    # Generate embeddings
    print("🔄 Encoding 5 sample texts...")
    embeddings = service.encode(texts, batch_size=5)

    print(f"✅ Generated {len(embeddings)} embeddings")
    print(f"   Embedding dimension: {len(embeddings[0])}")
    print(f"   First 5 values: {embeddings[0][:5]}")

    # Store to database
    print("💾 Storing embeddings to database...")
    db_service = PostgresJobExportService(db_url=db_url)

    embeddings_data = []
    for job, text, embedding in zip(
        jobs, texts, embeddings, strict=False
    ):
        embeddings_data.append(
            {
                "jobid": job[0],
                "text": text,
                "embedding": embedding,
                "source_jobid": job[0],
            }
        )

    inserted = db_service.insert_job_embeddings(embeddings_data)
    print(f"✅ Inserted {inserted} embeddings")

    print("\n✅ TEST PASSED - Embeddings working!")


if __name__ == "__main__":
    main()
