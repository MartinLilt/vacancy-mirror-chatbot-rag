import os
import unittest
from unittest import mock

from baltic_marketplace.services.upwork import (
    UpworkConfig,
    UpworkService,
    UpworkServiceError,
    _extract_public_search_jobs,
)


class UpworkServiceTests(unittest.TestCase):
    def test_config_from_env_prefers_access_token(self):
        with mock.patch.dict(
            os.environ,
            {
                "UPWORK_ACCESS_TOKEN": "token-1",
                "UPWORK_CLIENT_ID": "client-id",
                "UPWORK_CLIENT_SECRET": "client-secret",
                "UPWORK_REFRESH_TOKEN": "refresh-token",
            },
            clear=True,
        ):
            config = UpworkConfig.from_env()

        self.assertEqual(config.access_token, "token-1")
        self.assertEqual(config.client_id, "client-id")

    def test_config_from_env_accepts_refresh_flow(self):
        with mock.patch.dict(
            os.environ,
            {
                "UPWORK_CLIENT_ID": "client-id",
                "UPWORK_CLIENT_SECRET": "client-secret",
                "UPWORK_REFRESH_TOKEN": "refresh-token",
            },
            clear=True,
        ):
            config = UpworkConfig.from_env()

        self.assertIsNone(config.access_token)
        self.assertEqual(config.refresh_token, "refresh-token")

    def test_config_from_env_raises_when_missing_credentials(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(UpworkServiceError):
                UpworkConfig.from_env()

    def test_extract_public_search_jobs_reads_jobs_array(self):
        jobs = _extract_public_search_jobs(
            {
                "data": {
                    "publicMarketplaceJobPostingsSearch": {
                        "jobs": [{"title": "A"}, {"title": "B"}]
                    }
                }
            }
        )
        self.assertEqual(len(jobs), 2)

    def test_normalize_public_job_maps_upwork_fields(self):
        service = UpworkService(UpworkConfig(access_token="token"))

        normalized = service._normalize_public_job(
            {
                "recno": 123,
                "ciphertext": "abc123",
                "title": "Senior Full-Stack Developer",
                "description": "Build and maintain web apps",
                "createdDateTime": "2026-03-23T10:00:00Z",
                "jobStatus": "OPEN",
                "contractorTier": "EXPERT",
                "type": "FIXED_PRICE",
                "engagement": "FULL_TIME",
                "skills": [
                    {"prettyName": "React", "name": "react"},
                    {"prettyName": "", "name": "node.js"},
                ],
            }
        )

        self.assertEqual(normalized["uid"], "abc123")
        self.assertEqual(normalized["externalLink"], "https://www.upwork.com/jobs/~abc123")
        self.assertEqual(normalized["skills"], ["React", "node.js"])
        self.assertEqual(normalized["publishedAt"], "2026-03-23T10:00:00Z")

