from datetime import datetime, timezone
import tempfile
import unittest

from media_digest.models import Item
from media_digest.store import DigestStore


class StoreTest(unittest.TestCase):
    def test_filter_unseen_only_excludes_marked_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DigestStore(f"{tmp}/digest.db")
            try:
                items = [
                    Item(
                        source_id="github",
                        source_name="GitHub",
                        title=f"repo-{index}",
                        url=f"https://github.com/example/repo-{index}",
                        published_at=datetime(2026, 1, index + 1, tzinfo=timezone.utc),
                    )
                    for index in range(3)
                ]

                self.assertEqual(len(store.filter_unseen(items)), 3)
                store.mark_seen(items[:1])

                unseen = store.filter_unseen(items)
                self.assertEqual([item.title for item in unseen], ["repo-1", "repo-2"])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
