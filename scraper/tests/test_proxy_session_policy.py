from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from scraper.services.upwork_scraper import UpworkScraperService


class ProxySessionPolicyTests(unittest.TestCase):
    def test_rotate_on_session_ttl(self) -> None:
        svc = UpworkScraperService(proxy_url="http://user:pass@proxy.example:80")
        svc.flaresolverr_session_ttl_sec = 10
        svc._proxy_session_started_at = time.time() - 30

        with patch.object(svc, "_rotate_flaresolverr_proxy_session") as rotate:
            svc._maybe_rotate_proxy_session_before_request()

        rotate.assert_called_once_with("session_ttl")

    def test_rotate_on_request_cap(self) -> None:
        svc = UpworkScraperService(proxy_url="http://user:pass@proxy.example:80")
        svc.flaresolverr_max_requests_per_session = 5
        svc._proxy_session_started_at = time.time()
        svc._proxy_session_requests = 5

        with patch.object(svc, "_rotate_flaresolverr_proxy_session") as rotate:
            svc._maybe_rotate_proxy_session_before_request()

        rotate.assert_called_once_with("session_request_cap")

    def test_ensure_flaresolverr_session_reuses_existing(self) -> None:
        svc = UpworkScraperService(proxy_url="http://user:pass@proxy.example:80")
        svc.flaresolverr.create_session = MagicMock(return_value="vm-session-1")

        first = svc._ensure_flaresolverr_session()
        second = svc._ensure_flaresolverr_session()

        self.assertEqual("vm-session-1", first)
        self.assertEqual("vm-session-1", second)
        svc.flaresolverr.create_session.assert_called_once()

    def test_close_flaresolverr_session_resets_id(self) -> None:
        svc = UpworkScraperService(proxy_url="http://user:pass@proxy.example:80")
        svc._flaresolverr_session_id = "vm-session-1"
        svc.flaresolverr.destroy_session = MagicMock()

        svc._close_flaresolverr_session()

        svc.flaresolverr.destroy_session.assert_called_once_with("vm-session-1")
        self.assertIsNone(svc._flaresolverr_session_id)

    def test_with_rotated_session_for_webshare_username(self) -> None:
        rotated = UpworkScraperService._with_rotated_session("gpmsntlv-us-740741")
        self.assertIsNotNone(rotated)
        assert rotated is not None
        self.assertTrue(rotated.startswith("gpmsntlv-us-740741-session-"))


if __name__ == "__main__":
    unittest.main()

