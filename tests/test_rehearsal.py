import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

class RehearsalTests(unittest.TestCase):
    def test_separate_processes_and_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"run"
            cmd=[sys.executable,"-m","tbp.rehearsal","run",str(out)]
            subprocess.run(cmd,check=True,capture_output=True,env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"})
            verify=[sys.executable,"-m","tbp.rehearsal","verify",str(out)]
            result=subprocess.run(verify,check=True,capture_output=True)
            self.assertIn(b"FIXTURE PASS",result.stdout)
            self.assertTrue((out/"manifest.json").exists())
            with (out/"t1/response.json").open("ab") as file: file.write(b" ")
            self.assertNotEqual(subprocess.run(verify,capture_output=True).returncode,0)
