import unittest
from unittest.mock import patch, MagicMock

from modules import Sessions_Manager


class TestSessionManager(unittest.TestCase):
    @patch("modules.Sessions_Manager.requests.get")
    def test_verify_session_valid(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = "https://www.instagram.com/api/v1/accounts/edit/web_form_data/"
        mock_resp.json.return_value = {"form_data": {"username": "testuser"}}
        mock_get.return_value = mock_resp

        is_valid, msg = Sessions_Manager.verify_session("testuser", "12345:token:16:sig")
        self.assertTrue(is_valid)
        self.assertIn("valid", msg.lower())

    @patch("modules.Sessions_Manager.requests.get")
    def test_verify_session_redirects_to_login(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 302
        mock_resp.url = "https://www.instagram.com/accounts/login/"
        mock_get.return_value = mock_resp

        is_valid, msg = Sessions_Manager.verify_session("testuser", "12345:badtoken:16:sig")
        self.assertFalse(is_valid)
        self.assertIn("invalid", msg.lower())


if __name__ == "__main__":
    unittest.main()
