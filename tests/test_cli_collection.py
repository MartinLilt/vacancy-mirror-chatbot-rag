import argparse
import csv
import json
import tempfile
import unittest
from pathlib import Path

from baltic_marketplace.cli import (
    _job_dedupe_key,
    normalize_market_patterns_command,
    show_market_top_frequencies_command,
)


class CliCollectionTests(unittest.TestCase):
    def test_job_dedupe_key_prefers_uid(self):
        key = _job_dedupe_key(
            {
                "uid": "job-1",
                "externalLink": "https://example.com/job-1",
                "title": "Web Developer",
                "publishedAt": "2026-03-22",
            }
        )
        self.assertEqual(key, "job-1")

    def test_job_dedupe_key_falls_back_to_link(self):
        key = _job_dedupe_key(
            {
                "uid": "",
                "externalLink": "https://example.com/job-2",
                "title": "Web Developer",
                "publishedAt": "2026-03-22",
            }
        )
        self.assertEqual(key, "https://example.com/job-2")

    def test_show_market_top_frequencies_creates_three_separate_csv_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "jobs.json"
            skills_path = temp_path / "skills.csv"
            title_path = temp_path / "title.csv"
            description_path = temp_path / "description.csv"

            input_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "title": "Senior Full Stack Developer",
                                "description": "Build scalable web applications with clean architecture",
                                "skills": ["React", "Node.js", "React"],
                            },
                            {
                                "title": "Full Stack Developer Needed",
                                "description": "Build scalable products with clean code",
                                "skills": ["Node.js", "TypeScript"],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = show_market_top_frequencies_command(
                argparse.Namespace(
                    input=str(input_path),
                    top=10,
                    min_word_length=4,
                    skills_output=str(skills_path),
                    title_output=str(title_path),
                    description_output=str(description_path),
                )
            )

            self.assertEqual(result, 0)
            self.assertTrue(skills_path.exists())
            self.assertTrue(title_path.exists())
            self.assertTrue(description_path.exists())

            with skills_path.open("r", encoding="utf-8", newline="") as skills_file:
                skills_rows = list(csv.DictReader(skills_file))
            with title_path.open("r", encoding="utf-8", newline="") as title_file:
                title_rows = list(csv.DictReader(title_file))
            with description_path.open("r", encoding="utf-8", newline="") as description_file:
                description_rows = list(csv.DictReader(description_file))

            self.assertEqual(skills_rows[0], {"value": "React", "count": "2"})
            self.assertEqual(title_rows[0], {"pattern_type": "bigram", "value": "full stack", "count": "2"})
            self.assertEqual(
                description_rows[0],
                {"pattern_type": "bigram", "value": "build scalable", "count": "2"},
            )
            self.assertNotIn("job_ids", skills_rows[0])

    def test_normalize_market_patterns_command_merges_lowercase_and_special_symbols(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            title_input_path = temp_path / "title.csv"
            description_input_path = temp_path / "description.csv"
            title_output_path = temp_path / "title_normalized.csv"
            description_output_path = temp_path / "description_normalized.csv"

            with title_input_path.open("w", encoding="utf-8", newline="") as title_file:
                writer = csv.DictWriter(title_file, fieldnames=["pattern_type", "value", "count"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"pattern_type": "bigram", "value": "Full-Stack", "count": 3},
                        {"pattern_type": "bigram", "value": "full stack", "count": 2},
                        {"pattern_type": "trigram", "value": "Full Stack Developer", "count": 4},
                    ]
                )

            with description_input_path.open("w", encoding="utf-8", newline="") as description_file:
                writer = csv.DictWriter(description_file, fieldnames=["pattern_type", "value", "count"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"pattern_type": "bigram", "value": "Clean/Code", "count": 5},
                        {"pattern_type": "bigram", "value": "clean code", "count": 1},
                    ]
                )

            result = normalize_market_patterns_command(
                argparse.Namespace(
                    title_input=str(title_input_path),
                    description_input=str(description_input_path),
                    title_output=str(title_output_path),
                    description_output=str(description_output_path),
                )
            )

            self.assertEqual(result, 0)

            with title_output_path.open("r", encoding="utf-8", newline="") as title_file:
                title_rows = list(csv.DictReader(title_file))
            with description_output_path.open("r", encoding="utf-8", newline="") as description_file:
                description_rows = list(csv.DictReader(description_file))

            self.assertEqual(title_rows[0], {"pattern_type": "bigram", "value": "full stack", "count": "5"})
            self.assertEqual(
                title_rows[1],
                {"pattern_type": "trigram", "value": "full stack developer", "count": "4"},
            )
            self.assertEqual(
                description_rows[0],
                {"pattern_type": "bigram", "value": "clean code", "count": "6"},
            )
