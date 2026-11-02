import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import app_updates as update

class UpdateTests(unittest.TestCase):
    def test_retry_after_temporary_connection_failure(self):
        session=MagicMock()
        response=MagicMock(status_code=200)
        session.get.side_effect=[update.requests.ConnectionError("offline"),response]
        with patch.object(update.time,'sleep'):
            self.assertIs(update.release_response(session,{}),response)
        self.assertEqual(session.get.call_count,2)

    def test_exhausted_connection_has_clear_error(self):
        session=MagicMock()
        session.get.side_effect=update.requests.ConnectionError("private transport details")
        with patch.object(update.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'three attempts') as failure:
                update.release_response(session,{})
        self.assertNotIn('private transport',str(failure.exception))

    def info(self, data=b'MZtest'):
        return dict(status='available',latest='v1.5.0',name='OG-Studio-v1.5.0-windows-x64.exe',asset_id=8,size=len(data),sha256=hashlib.sha256(data).hexdigest())

    def test_versions_are_numeric(self):
        self.assertGreater(update.version_tuple('v1.10.0'),update.version_tuple('v1.9.0'))
        self.assertEqual(update.version_tuple('v1.2'),(1,2,0))
        with self.assertRaises(ValueError):update.version_tuple('v1.5.0-beta')

    def test_available_release(self):
        with patch.object(update.requests,'Session') as sessions:
            response=sessions.return_value.__enter__.return_value.get.return_value
            response.status_code=200
            response.json.return_value=dict(tag_name='v1.5.0',assets=[dict(name='OG-Studio-v1.5.0-windows-x64.exe',state='uploaded',id=8,size=6,digest='sha256:'+'a'*64,url=update.API+'/releases/assets/8')])
            self.assertEqual(update.check_update()['status'],'available')

    def test_private_repo_without_credentials_has_browser_fallback(self):
        with patch.object(update.requests,'Session') as sessions,patch.object(update,'github_token',return_value=None):
            sessions.return_value.__enter__.return_value.get.return_value.status_code=404
            self.assertEqual(update.check_update()['status'],'needs_access')

    def test_checksum_and_auth_is_not_sent_to_cdn(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(update.requests,'Session') as sessions,patch.object(update,'github_token',return_value='secret'):
            session=sessions.return_value.__enter__.return_value
            redirect=MagicMock(status_code=302,headers={'location':'https://release-assets.githubusercontent.com/test'})
            response=MagicMock(status_code=200)
            response.iter_content.return_value=[b'MZ',b'test']
            session.get.side_effect=[redirect,response]
            path=update.download_update(self.info(),folder,MagicMock())
            self.assertEqual(Path(path).read_bytes(),b'MZtest')
            self.assertIn('Authorization',session.get.call_args_list[0].kwargs['headers'])
            self.assertNotIn('Authorization',session.get.call_args_list[1].kwargs['headers'])

    def test_corrupt_download_never_becomes_executable(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(update.requests,'Session') as sessions,patch.object(update,'github_token',return_value=None):
            response=sessions.return_value.__enter__.return_value.get.return_value
            response.status_code=200
            response.iter_content.return_value=[b'MZnope']
            with self.assertRaisesRegex(RuntimeError,'integrity'):
                update.download_update(self.info(),folder,MagicMock())
            self.assertFalse(list(Path(folder).iterdir()))
