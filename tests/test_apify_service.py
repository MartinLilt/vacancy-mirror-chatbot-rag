import unittest

from baltic_marketplace.apify.service import ApifyService, ApifyServiceError


class FakeApifyClient:
    def __init__(self, actor_id, response):
        self._config = type("Config", (), {"actor_id": actor_id})()
        self.response = response
        self.calls = []

    def run_actor_sync(self, input_payload):
        self.calls.append(input_payload)
        return self.response


class ApifyServiceTests(unittest.TestCase):
    def test_fetch_profile_posts_builds_expected_actor_input(self):
        client = FakeApifyClient(
            "benjarapi/linkedin-user-posts",
            [{"postUrl": "https://www.linkedin.com/feed/update/test"}],
        )

        payload = ApifyService(client).fetch_linkedin_profile_posts(
            profile_url="https://www.linkedin.com/in/martin-liminovic-44046b21a/",
            max_posts=7,
        )

        self.assertEqual(payload["source"], "apify")
        self.assertEqual(
            payload["actorId"], "benjarapi/linkedin-user-posts"
        )
        self.assertEqual(
            client.calls[0]["profile"],
            "https://www.linkedin.com/in/martin-liminovic-44046b21a",
        )
        self.assertEqual(client.calls[0]["maxPosts"], 7)

    def test_fetch_profile_posts_rejects_invalid_max_posts(self):
        client = FakeApifyClient("benjarapi/linkedin-user-posts", [])

        with self.assertRaises(ApifyServiceError) as ctx:
            ApifyService(client).fetch_linkedin_profile_posts(
                profile_url="https://www.linkedin.com/in/martin-liminovic-44046b21a/",
                max_posts=0,
            )

        self.assertIn("max-posts", str(ctx.exception))

    def test_fetch_profile_post_summaries_returns_compact_shape(self):
        client = FakeApifyClient(
            "benjarapi/linkedin-user-posts",
            [
                {
                    "text": "Post body",
                    "stats": {"total_reactions": 5, "comments": 2},
                    "media": {"url": "https://example.com/image.jpg"},
                }
            ],
        )

    def test_fetch_profile_post_dataset_returns_normalized_posts(self):
        client = FakeApifyClient(
            "benjarapi/linkedin-user-posts",
            [
                {
                    "full_urn": "urn:li:activity:1",
                    "text": "Post body",
                    "url": "https://linkedin.com/posts/1",
                    "posted_at": {"date": "2026-03-21 10:00:00", "timestamp": 123},
                    "stats": {"total_reactions": 5, "comments": 2},
                    "media": {"url": "https://example.com/image.jpg"},
                }
            ],
        )

        dataset = ApifyService(client).fetch_linkedin_profile_post_dataset(
            profile_url="https://www.linkedin.com/in/martin-liminovic-44046b21a/",
            max_posts=1,
        )

        self.assertEqual(dataset["profileUrl"], "https://www.linkedin.com/in/martin-liminovic-44046b21a")
        self.assertEqual(
            dataset["posts"],
            [
                {
                    "id": "urn:li:activity:1",
                    "text": "Post body",
                    "url": "https://linkedin.com/posts/1",
                    "posted_at": "2026-03-21 10:00:00",
                    "posted_timestamp": 123,
                    "likes": 5,
                    "comments": 2,
                    "image_url": "https://example.com/image.jpg",
                }
            ],
        )

        summaries = ApifyService(client).fetch_linkedin_profile_post_summaries(
            profile_url="https://www.linkedin.com/in/martin-liminovic-44046b21a/",
            max_posts=1,
        )

        self.assertEqual(
            summaries,
            [
                {
                    "text": "Post body",
                    "likes": 5,
                    "comments": 2,
                    "image_url": "https://example.com/image.jpg",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
