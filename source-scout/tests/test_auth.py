import unittest

from source_scout.auth import SessionManager


class SessionManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = SessionManager("admin", "correct horse", "s" * 32, 86_400)

    def test_credential_verification(self):
        self.assertTrue(self.manager.verify_credentials("admin", "correct horse"))
        self.assertFalse(self.manager.verify_credentials("wrong", "correct horse"))
        self.assertFalse(self.manager.verify_credentials("admin", "wrong"))

    def test_valid_session_lasts_24_hours(self):
        token = self.manager.issue(now=1_000)
        self.assertTrue(self.manager.validate(token, now=1_000 + 43_200))
        self.assertTrue(self.manager.validate(token, now=1_000 + 86_399))
        self.assertFalse(self.manager.validate(token, now=1_000 + 86_400))

    def test_tampered_session_is_rejected(self):
        token = self.manager.issue(now=1_000)
        self.assertFalse(self.manager.validate(token + "tampered", now=1_001))

    def test_cookie_is_http_only(self):
        cookie = self.manager.cookie_header("token", secure=True)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("Max-Age=86400", cookie)

    def test_lifetime_cannot_be_less_than_12_hours(self):
        with self.assertRaises(ValueError):
            SessionManager("admin", "password", "s" * 32, 43_199)


if __name__ == "__main__":
    unittest.main()
