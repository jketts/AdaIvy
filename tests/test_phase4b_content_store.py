from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from math_research.phase4a.content_store import ContentStoreError
from math_research.phase4a.serialization import sha256_bytes
from math_research.phase4b import MAX_SOURCE_BYTES
from math_research.phase4b.content_store import Phase4BContentStore


class Phase4BContentStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = Phase4BContentStore(Path(self.temporary.name) / "content")

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def test_identical_bytes_remain_independently_deletable(self) -> None:
        data = b"same project-authored bytes"
        digest = sha256_bytes(data)
        first = self.store.publish("source.first", data, expected_hash=digest)
        second = self.store.publish("source.second", data, expected_hash=digest)
        self.assertNotEqual(first, second)
        self.store.verify_inventory({"source.first", "source.second"})
        self.store.remove("source.first")
        self.store.verify_absent("source.first")
        self.assertEqual(data, self.store.read("source.second", expected_hash=digest))
        self.store.verify_inventory({"source.second"})

    def test_hash_and_size_fail_before_publication(self) -> None:
        with self.assertRaisesRegex(ContentStoreError, "hash differs"):
            self.store.publish("source.bad", b"bytes", expected_hash=sha256_bytes(b"other"))
        with self.assertRaisesRegex(ValueError, "byte bound"):
            self.store.publish(
                "source.large",
                b"x" * (MAX_SOURCE_BYTES + 1),
                expected_hash=sha256_bytes(b"x" * (MAX_SOURCE_BYTES + 1)),
            )
        self.store.verify_inventory(set())

    def test_substitution_or_unexpected_content_fails_inventory(self) -> None:
        data = b"bytes"
        digest = sha256_bytes(data)
        self.store.publish("source.one", data, expected_hash=digest)
        unexpected = self.store.root / "objects" / "unexpected"
        unexpected.mkdir()
        with self.assertRaisesRegex(ContentStoreError, "inventory drift"):
            self.store.verify_inventory({"source.one"})


if __name__ == "__main__":
    unittest.main()
