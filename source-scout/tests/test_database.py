import tempfile
import unittest
from pathlib import Path

from source_scout.database import Database


class DatabaseTests(unittest.TestCase):
    def test_mobile_token_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.db")
            created = database.create_mobile_token("iPhone", "hashed-token")
            self.assertTrue(database.validate_mobile_token("hashed-token"))
            self.assertTrue(database.revoke_mobile_token(created["id"]))
            self.assertFalse(database.validate_mobile_token("hashed-token"))


if __name__ == "__main__":
    unittest.main()
