import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from project_store import write_project


class ProjectWriteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "session.json"
        self.path.write_text('{"previous":"safe"}')

    def test_temporary_access_denial_is_retried(self):
        replace = os.replace
        with patch("project_store.os.replace",side_effect=[PermissionError("Locked"),PermissionError("Locked"),None]) as mocked, patch("project_store.time.sleep"):
            # Perform the real replacement on the successful attempt.
            def attempt(source,target):
                if mocked.call_count<3:
                    raise PermissionError("Locked")
                return replace(source,target)
            mocked.side_effect=attempt
            write_project(self.path,{"new":"saved"})
            self.assertEqual(mocked.call_count,3)
        self.assertEqual(json.loads(self.path.read_text()),{"new":"saved"})

    def test_persistent_denial_preserves_previous_good_save(self):
        with patch("project_store.os.replace",side_effect=PermissionError("Locked")),patch("project_store.time.sleep"):
            with self.assertRaises(PermissionError):
                write_project(self.path,{"new":"not saved"})
        self.assertEqual(json.loads(self.path.read_text()),{"previous":"safe"})
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    @unittest.skipUnless(os.name=="nt","Windows file sharing semantics")
    def test_real_windows_file_lock_is_recovered(self):
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.CreateFileW(str(self.path),0x80000000,1,None,3,0x80,None)
        if handle==ctypes.c_void_p(-1).value:
            self.fail(f"Could not establish test lock: {ctypes.get_last_error()}")
        release=threading.Timer(.15,lambda:kernel.CloseHandle(handle))
        release.start()
        try:
            write_project(self.path,{"new":"saved after actual Windows lock"})
        finally:
            release.join()
        self.assertEqual(json.loads(self.path.read_text())["new"],"saved after actual Windows lock")


if __name__ == "__main__":
    unittest.main()
