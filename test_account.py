import unittest
from unittest.mock import patch, MagicMock
import videoexpress_automation as automation

class AccountTests(unittest.TestCase):
    def test_no_session_needs_login(self):
        with patch.object(automation, 'AUTH_STATE_PATH') as auth, patch.object(automation, 'sync_playwright') as pw:
            auth.exists.return_value=False
            self.assertEqual(automation.check_saved_session(), 'missing')
            pw.assert_not_called()

    def test_connection_states(self):
        for status, payload, expected in [(200, {'results': []}, 'connected'), (401, {}, 'expired'), (503, {}, 'unavailable')]:
            with self.subTest(status=status), patch.object(automation, 'AUTH_STATE_PATH') as auth, patch.object(automation, 'sync_playwright') as pw:
                auth.exists.return_value=True
                request=pw.return_value.__enter__.return_value.request.new_context.return_value
                response=request.get.return_value
                response.status=status
                response.ok=status==200
                response.json.return_value=payload
                self.assertEqual(automation.check_saved_session(), expected)
                request.dispose.assert_called_once()

    def test_timeout_preserves_saved_session(self):
        with patch.object(automation, 'AUTH_STATE_PATH') as auth, patch.object(automation, 'sync_playwright') as pw:
            auth.exists.return_value=True
            request=pw.return_value.__enter__.return_value.request.new_context.return_value
            request.get.side_effect=RuntimeError('Timeout cookie: private')
            self.assertEqual(automation.check_saved_session(), 'unavailable')
            auth.unlink.assert_not_called()
            request.dispose.assert_called_once()
