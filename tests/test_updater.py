import hashlib
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
UPDATER_PATH = REPOSITORY_ROOT / "tools" / "Update-And-Run.ps1"
ASSET_NAME = "WeChatPatResponder-Windows-x64.zip"


class UpdaterTests(unittest.TestCase):
    def create_package(self, directory, extra_entries=None):
        package_path = directory / ASSET_NAME
        entries = {
            "WeChatPatResponder.exe": b"MZ" + b"\0" * (1024 * 1024),
            "Run.cmd": b"@echo updated\r\n",
            "Update-and-Run.cmd": b"@echo updater\r\n",
            "CHANGELOG.md": b"# Changelog\r\n\r\n## 9.9.9\r\n",
            "tools/Update-And-Run.ps1": b"Write-Host updated\r\n",
        }
        entries.update(extra_entries or {})
        with zipfile.ZipFile(
            package_path,
            "w",
            compression=zipfile.ZIP_STORED,
        ) as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
        return package_path

    def create_metadata(self, directory, package_path, digest=None):
        actual_digest = hashlib.sha256(package_path.read_bytes()).hexdigest()
        metadata = {
            "tag_name": "v9.9.9",
            "assets": [
                {
                    "name": ASSET_NAME,
                    "size": package_path.stat().st_size,
                    "digest": digest or f"sha256:{actual_digest}",
                    "browser_download_url": "https://example.invalid/package.zip",
                }
            ],
        }
        metadata_path = directory / "release.json"
        metadata_path.write_text(
            json.dumps(metadata),
            encoding="utf-8",
        )
        return metadata_path

    def run_updater(self, app_directory, metadata_path, package_path=None):
        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(UPDATER_PATH),
            "-AppDirectory",
            str(app_directory),
            "-ReleaseMetadataPath",
            str(metadata_path),
        ]
        if package_path is not None:
            command.extend(["-PackagePath", str(package_path)])
        command.append("-NoStart")
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def test_update_replaces_release_files_and_preserves_runtime_data(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            app_directory = root / "app"
            app_directory.mkdir()
            (app_directory / "WeChatPatResponder.exe").write_bytes(b"old")
            (app_directory / "Run.cmd").write_text("old", encoding="utf-8")
            (app_directory / "CHANGELOG.md").write_text(
                "# Changelog\n\n## 1.0.0\n",
                encoding="utf-8",
            )
            (app_directory / "reply_history.txt").write_text(
                "keep history",
                encoding="utf-8",
            )
            (app_directory / "tickle_state.json").write_text(
                "keep state",
                encoding="utf-8",
            )
            package_path = self.create_package(root)
            metadata_path = self.create_metadata(root, package_path)

            result = self.run_updater(
                app_directory,
                metadata_path,
                package_path,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(
                (app_directory / "WeChatPatResponder.exe")
                .read_bytes()
                .startswith(b"MZ")
            )
            self.assertEqual(
                (app_directory / "CHANGELOG.md").read_text(encoding="utf-8"),
                "# Changelog\n\n## 9.9.9\n",
            )
            self.assertEqual(
                (app_directory / "reply_history.txt").read_text(
                    encoding="utf-8"
                ),
                "keep history",
            )
            self.assertEqual(
                (app_directory / "tickle_state.json").read_text(
                    encoding="utf-8"
                ),
                "keep state",
            )

    def test_bad_digest_does_not_replace_existing_installation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            app_directory = root / "app"
            app_directory.mkdir()
            executable = app_directory / "WeChatPatResponder.exe"
            executable.write_bytes(b"old executable")
            package_path = self.create_package(root)
            metadata_path = self.create_metadata(
                root,
                package_path,
                digest="sha256:" + "0" * 64,
            )

            result = self.run_updater(
                app_directory,
                metadata_path,
                package_path,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(executable.read_bytes(), b"old executable")

    def test_path_traversal_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            app_directory = root / "app"
            app_directory.mkdir()
            executable = app_directory / "WeChatPatResponder.exe"
            executable.write_bytes(b"old executable")
            package_path = self.create_package(
                root,
                {"../escape.txt": b"must not escape"},
            )
            metadata_path = self.create_metadata(root, package_path)

            result = self.run_updater(
                app_directory,
                metadata_path,
                package_path,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(executable.read_bytes(), b"old executable")
            self.assertFalse((root / "escape.txt").exists())

    def test_same_release_skips_the_download(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            app_directory = root / "app"
            app_directory.mkdir()
            (app_directory / "CHANGELOG.md").write_text(
                "# Changelog\n\n## 9.9.9\n",
                encoding="utf-8",
            )
            package_path = self.create_package(root)
            metadata_path = self.create_metadata(root, package_path)

            result = self.run_updater(app_directory, metadata_path)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Already current: v9.9.9", result.stdout)

    def test_install_failure_rolls_back_replaced_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            app_directory = root / "app"
            app_directory.mkdir()
            executable = app_directory / "WeChatPatResponder.exe"
            executable.write_bytes(b"old executable")
            changelog = app_directory / "CHANGELOG.md"
            changelog.write_text(
                "# Changelog\n\n## 1.0.0\n",
                encoding="utf-8",
            )
            (app_directory / "blocked").write_text(
                "parent is deliberately a file",
                encoding="utf-8",
            )
            package_path = self.create_package(
                root,
                {"blocked/file.txt": b"force a copy failure"},
            )
            metadata_path = self.create_metadata(root, package_path)

            result = self.run_updater(
                app_directory,
                metadata_path,
                package_path,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(executable.read_bytes(), b"old executable")
            self.assertEqual(
                changelog.read_text(encoding="utf-8"),
                "# Changelog\n\n## 1.0.0\n",
            )


if __name__ == "__main__":
    unittest.main()
