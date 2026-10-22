"""Exercise the actual bash launcher, virtualenv, prompts and fresh-process load.

Only the storage path is redirected by a test-only sitecustomize. The launcher,
getpass, setup, validation, atomic write and configuration parser are real.
"""

import os as _platform_os
import unittest as _platform_tests
if _platform_os.name == "nt":
    raise _platform_tests.SkipTest("Legacy POSIX launcher/permissions/deadline tests; Windows desktop has dedicated tests")

import errno
import json
import os
from pathlib import Path
import pty
import select
import signal
import stat
import subprocess
import tempfile
import time
import unittest


class SetupPtyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(__file__).resolve().parents[1]
        self.config = Path(self.temp.name) / "iris" / "config.env"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("IRIS_")}
        self.env.update(IRIS_TEST_CONFIG_PATH=str(self.config), PYTHONDONTWRITEBYTECODE="1",
                        PYTHONPATH=os.pathsep.join((str(self.root / "tests" / "setup_pty_support"), str(self.root))))

    def run_setup(self, *, provider="", key="", fish=""):
        child, descriptor = pty.fork()
        if child == 0:
            os.chdir(self.temp.name)
            os.execve(str(self.root / "iris-run"), [str(self.root / "iris-run"), "setup"], self.env)
        output = bytearray()
        pending = bytearray()
        deadline = time.monotonic() + 20
        reaped = False

        def read_until(token):
            while token not in pending:
                if time.monotonic() >= deadline:
                    self.fail("Setup PTY exceeded its test deadline.")
                if not select.select([descriptor], [], [], 0.1)[0]:
                    continue
                try:
                    chunk = os.read(descriptor, 4096)
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        chunk = b""
                    else:
                        raise
                if not chunk:
                    self.fail("Setup PTY exited before the expected prompt; output withheld.")
                output.extend(chunk)
                pending.extend(chunk)
            end = pending.index(token) + len(token)
            del pending[:end]

        try:
            prompts = [
                (b"Provider: groq or ollama", provider), (b"Provider base URL", ""),
                (b"Model ID for all roles", ""), (b"Provider API key", key),
                (b"Vosk model directory", ""), (b"Fish API key", fish),
                (b"Fish voice ID", ""), (b"Fish model", ""),
            ]
            for prompt, answer in prompts:
                read_until(prompt)
                read_until(b": ")
                os.write(descriptor, (answer + "\n").encode())
            read_until(b"IRIS configuration saved.")
            while time.monotonic() < deadline:
                pid, status = os.waitpid(child, os.WNOHANG)
                if pid:
                    reaped = True
                    self.assertEqual(os.waitstatus_to_exitcode(status), 0)
                    break
                time.sleep(0.01)
            self.assertTrue(reaped, "Setup did not exit after saving.")
            for value in (key, fish):
                if value:
                    self.assertFalse(value.encode() in output, "Hidden input was echoed.")
        finally:
            if not reaped:
                os.kill(child, signal.SIGKILL)
                os.waitpid(child, 0)
            os.close(descriptor)

    def fresh_load(self):
        # The fresh process inherits NO IRIS provider/key settings. Only the
        # temporary path selection crosses the process boundary.
        code = '''
import json
from iris.local_config import read_saved
from iris.terminal import load_config
saved = read_saved()
c = load_config()
print(json.dumps({"groq": c.fast_target.provider == "groq",
 "model": c.fast_target.model == "openai/gpt-oss-20b",
 "provider_key_retained": c.provider.api_key == "fixture-provider-no-service",
 "fish_key_retained": saved.get("IRIS_FISH_API_KEY") == "fixture-fish-no-service"}))
'''
        result = subprocess.run([str(self.root / ".venv" / "bin" / "python"), "-B", "-c", code],
                                env=self.env, cwd=self.temp.name, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, "Fresh-process config load failed; output withheld.")
        return json.loads(result.stdout)

    def test_real_launcher_saves_hidden_keys_and_fresh_process_loads_them(self):
        self.run_setup(provider="groq", key="fixture-provider-no-service", fish="fixture-fish-no-service")
        self.assertTrue(all(self.fresh_load().values()))
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.config.parent.stat().st_mode), 0o700)
        self.run_setup()
        self.assertTrue(all(self.fresh_load().values()))

    def test_setup_tightens_existing_user_owned_permissions_without_losing_keys(self):
        self.run_setup(key="fixture-provider-no-service", fish="fixture-fish-no-service")
        self.config.chmod(0o644)
        self.config.parent.chmod(0o755)
        self.run_setup()
        self.assertTrue(all(self.fresh_load().values()))
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.config.parent.stat().st_mode), 0o700)

    def test_launcher_reports_unsafe_symlink_without_modifying_target(self):
        self.config.parent.mkdir(mode=0o700)
        target = Path(self.temp.name) / "private-fixture"
        target.write_text("synthetic-private-value", encoding="utf-8")
        target.chmod(0o600)
        self.config.symlink_to(target)
        result = subprocess.run([str(self.root / "iris-run"), "setup"], env=self.env,
                                cwd=self.temp.name, input="", capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertTrue("stage=private_permissions" in result.stdout)
        self.assertTrue("exception=LocalConfigError" in result.stdout)
        self.assertFalse("synthetic-private-value" in result.stdout)
        self.assertFalse(str(target) in result.stdout)
        self.assertTrue(target.read_text(encoding="utf-8") == "synthetic-private-value")


if __name__ == "__main__":
    unittest.main()
