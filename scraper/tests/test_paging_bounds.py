from __future__ import annotations

import unittest

from scraper.paging_bounds import bounded_real_max_from_paging


class PagingBoundsTests(unittest.TestCase):
    def test_init_from_observed_total(self) -> None:
        real_max, decision = bounded_real_max_from_paging(
            paging_total=321,
            existing_real_max=0,
            per_page=50,
        )
        self.assertEqual(7, real_max)
        self.assertEqual("init", decision)

    def test_shrink_large_stale_overestimate(self) -> None:
        real_max, decision = bounded_real_max_from_paging(
            paging_total=321,
            existing_real_max=62,
            per_page=50,
        )
        self.assertEqual(9, real_max)
        self.assertEqual("shrunk", decision)

    def test_keep_when_gap_is_small(self) -> None:
        real_max, decision = bounded_real_max_from_paging(
            paging_total=2300,
            existing_real_max=50,
            per_page=50,
        )
        self.assertEqual(50, real_max)
        self.assertEqual("kept", decision)

    def test_raise_when_observed_is_higher(self) -> None:
        real_max, decision = bounded_real_max_from_paging(
            paging_total=2600,
            existing_real_max=40,
            per_page=50,
        )
        self.assertEqual(52, real_max)
        self.assertEqual("raised", decision)


if __name__ == "__main__":
    unittest.main()

