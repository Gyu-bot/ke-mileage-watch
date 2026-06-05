from __future__ import annotations

import json
import unittest
from pathlib import Path

from ke_watch.parser import parse_award_availability, summarize_available


class ParserTest(unittest.TestCase):
    def test_parse_fixture_has_expected_available_fares(self):
        fixture_path = Path('/tmp/ke_award_availability_sanitized.json')
        fixture = json.loads(fixture_path.read_text(encoding='utf-8'))
        flights = parse_award_availability(fixture['response'])
        rows = summarize_available(flights)

        self.assertEqual(len(flights), 14)
        self.assertTrue(any(r['flight'] == 'KE707' and r['cabin'] == 'prestige' and r['seats'] == 1 for r in rows))
        self.assertTrue(any(r['flight'] == 'KE704' and r['cabin'] == 'prestige' and r['seats'] == 7 for r in rows))
        self.assertTrue(all(r['seats'] > 0 for r in rows))


if __name__ == '__main__':
    unittest.main()
