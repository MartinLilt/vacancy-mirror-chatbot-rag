import unittest

from baltic_marketplace.cli import (
    _build_unique_job_pattern_hits,
    _cluster_similar_jobs,
    _prepare_pattern_classification_payload,
)


class MarketPatternPayloadTests(unittest.TestCase):
    def test_prepare_pattern_classification_payload_keeps_all_sections(self):
        payload = _prepare_pattern_classification_payload(
            {
                "title_bigrams": [{"value": "full stack", "count": 10, "job_ids": ["a", "b"]}],
                "title_trigrams": [{"value": "full stack developer", "count": 8, "job_ids": ["a"]}],
                "description_bigrams": [{"value": "tech stack", "count": 7, "job_ids": ["a"]}],
                "description_trigrams": [{"value": "clean maintainable code", "count": 4, "job_ids": ["b"]}],
                "skills": [{"value": "Node.js", "count": 9, "job_ids": ["a", "b"]}],
            },
            max_patterns_per_section=20,
            max_job_ids_per_pattern=5,
        )
        self.assertEqual(payload["title_bigrams"][0]["value"], "full stack")
        self.assertEqual(payload["skills"][0]["job_ids"], ["a", "b"])

    def test_prepare_pattern_classification_payload_limits_job_ids(self):
        payload = _prepare_pattern_classification_payload(
            {
                "title_bigrams": [
                    {
                        "value": "full stack",
                        "count": 10,
                        "job_ids": ["1", "2", "3", "4", "5", "6"],
                    }
                ]
            },
            max_patterns_per_section=20,
            max_job_ids_per_pattern=5,
        )
        self.assertEqual(payload["title_bigrams"][0]["job_ids"], ["1", "2", "3", "4", "5"])

    def test_build_unique_job_pattern_hits_merges_sections_per_job(self):
        rows = _build_unique_job_pattern_hits(
            {
                "title_bigrams": [{"value": "full stack", "count": 10, "job_ids": ["job-1", "job-2"]}],
                "title_trigrams": [{"value": "full stack developer", "count": 8, "job_ids": ["job-1"]}],
                "description_bigrams": [{"value": "tech stack", "count": 7, "job_ids": ["job-1"]}],
                "description_trigrams": [{"value": "clean maintainable code", "count": 4, "job_ids": ["job-2"]}],
                "skills": [{"value": "Node.js", "count": 9, "job_ids": ["job-1", "job-2"]}],
            }
        )
        self.assertEqual(rows[0]["job_id"], "job-1")
        self.assertEqual(rows[0]["total_pattern_hits"], 4)
        self.assertEqual(rows[1]["job_id"], "job-2")
        self.assertEqual(rows[1]["total_pattern_hits"], 3)

    def test_cluster_similar_jobs_groups_high_overlap_rows(self):
        clusters = _cluster_similar_jobs(
            [
                {
                    "job_id": "job-1",
                    "matched_title_bigrams": ["full stack", "backend developer"],
                    "matched_title_trigrams": ["full stack developer"],
                    "matched_description_bigrams": ["tech stack", "best practices"],
                    "matched_description_trigrams": ["clean maintainable code"],
                    "matched_skills": ["Node.js", "TypeScript"],
                    "total_pattern_hits": 8,
                },
                {
                    "job_id": "job-2",
                    "matched_title_bigrams": ["full stack", "backend developer"],
                    "matched_title_trigrams": ["full stack developer"],
                    "matched_description_bigrams": ["tech stack", "best practices"],
                    "matched_description_trigrams": ["clean maintainable code"],
                    "matched_skills": ["Node.js", "TypeScript"],
                    "total_pattern_hits": 8,
                },
                {
                    "job_id": "job-3",
                    "matched_title_bigrams": ["wordpress developer"],
                    "matched_title_trigrams": ["wordpress developer needed"],
                    "matched_description_bigrams": ["ideal candidate"],
                    "matched_description_trigrams": ["ideal candidate will"],
                    "matched_skills": ["WordPress"],
                    "total_pattern_hits": 5,
                },
            ],
            similarity_threshold=0.8,
        )
        self.assertEqual(len(clusters), 2)
        self.assertEqual(clusters[0]["size"], 2)
        self.assertEqual(clusters[0]["job_ids"], ["job-1", "job-2"])
