"""Offline safety regressions; every HTTP response is mocked."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest import mock

import ghdl


RAW = "https://raw.githubusercontent.com/owner/repo/main/data.bin"
PUBLIC = {"full_name": "owner/repo", "private": False, "visibility": "public"}


def zip_payload():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("README.txt", "public test content")
    return buffer.getvalue()


class Response:
    def __init__(self, body=b"payload", headers=None, error_after=False, on_read=None):
        self.body = io.BytesIO(body)
        self.headers = headers or {}
        self.status = 200
        self.error_after = error_after
        self.on_read = on_read
        self.reads = 0

    def read(self, size=-1):
        self.reads += 1
        if self.on_read:
            callback, self.on_read = self.on_read, None
            callback()
        if self.error_after and self.reads > 1:
            raise OSError("connection interrupted")
        return self.body.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.body.close()


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.dest = self.directory / "data.bin"
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def only_destination(self):
        self.assertEqual(sorted(p.name for p in self.directory.iterdir()), [self.dest.name])

    def test_existing_file_is_preserved_without_network(self):
        self.dest.write_bytes(b"original")
        with mock.patch("ghdl.urllib.request.urlopen", return_value=Response()) as fetch:
            with self.assertRaises(FileExistsError):
                ghdl.download_to(RAW, self.dest)
        self.assertEqual(self.dest.read_bytes(), b"original")
        fetch.assert_not_called()
        self.only_destination()

    def test_success_installs_complete_file(self):
        with mock.patch("ghdl.urllib.request.urlopen", return_value=Response(b"abc", {"Content-Length": "3"})):
            ghdl.download_to(RAW, self.dest)
        self.assertEqual(self.dest.read_bytes(), b"abc")
        self.only_destination()

    def test_interrupted_download_leaves_no_partial_file(self):
        with mock.patch("ghdl.urllib.request.urlopen", return_value=Response(b"partial", error_after=True)):
            with self.assertRaises(OSError):
                ghdl.download_to(RAW, self.dest)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_interrupted_overwrite_preserves_old_file(self):
        self.dest.write_bytes(b"original")
        with mock.patch("ghdl.urllib.request.urlopen", return_value=Response(b"partial", error_after=True)):
            with self.assertRaises(OSError):
                ghdl.download_to(RAW, self.dest, overwrite=True)
        self.assertEqual(self.dest.read_bytes(), b"original")
        self.only_destination()

    def test_explicit_overwrite_uses_atomic_replace(self):
        self.dest.write_bytes(b"original")
        with mock.patch("ghdl.urllib.request.urlopen", return_value=Response(b"new")), mock.patch("ghdl.os.replace", wraps=os.replace) as replace:
            ghdl.download_to(RAW, self.dest, overwrite=True)
        self.assertEqual(self.dest.read_bytes(), b"new")
        replace.assert_called_once()
        temporary, destination = replace.call_args.args
        self.assertEqual(Path(temporary).parent, self.dest.parent)
        self.assertNotEqual(Path(temporary), self.dest)
        self.assertEqual(Path(destination), self.dest)
        self.only_destination()

    def test_file_created_during_transfer_is_not_overwritten(self):
        response = Response(b"new", on_read=lambda: self.dest.write_bytes(b"racing writer"))
        with mock.patch("ghdl.urllib.request.urlopen", return_value=response):
            with self.assertRaises(FileExistsError):
                ghdl.download_to(RAW, self.dest)
        self.assertEqual(self.dest.read_bytes(), b"racing writer")
        self.only_destination()

    def test_empty_truncated_and_invalid_length_are_failures(self):
        cases = [(b"", {}), (b"abc", {"Content-Length": "5"}), (b"abc", {"Content-Length": "2"}), (b"abc", {"Content-Length": "-1"}), (b"abc", {"Content-Length": "garbage"})]
        for body, headers in cases:
            with self.subTest(body=body, headers=headers), mock.patch("ghdl.urllib.request.urlopen", return_value=Response(body, headers)):
                with self.assertRaises(OSError):
                    ghdl.download_to(RAW, self.dest)
                self.assertEqual(list(self.directory.iterdir()), [])

    def test_html_error_pages_are_not_successful_binary_downloads(self):
        cases = [(b"<!doctype html><html>Mirror unavailable</html>", {}), (b"<html><body>login</body></html>", {"Content-Type": "text/plain"}), (b"<!-- upstream gateway -->\n<html><body>Login required</body></html>", {"Content-Type": "text/plain"}), (b"access denied", {"Content-Type": "text/html; charset=utf-8"})]
        for body, headers in cases:
            with self.subTest(headers=headers), mock.patch("ghdl.urllib.request.urlopen", return_value=Response(body, headers)):
                with self.assertRaises(OSError):
                    ghdl.download_to(RAW, self.dest)
                self.assertEqual(list(self.directory.iterdir()), [])

    def test_requested_raw_html_is_allowed(self):
        target = RAW.replace("data.bin", "index.html")
        body = b"<!DOCTYPE html><html><body>Actual project page</body></html>"
        with mock.patch("ghdl.urllib.request.urlopen", return_value=Response(body, {"Content-Type": "text/html"})):
            ghdl.download_to("https://mirror.invalid/" + target, self.dest, target_url=target)
        self.assertEqual(self.dest.read_bytes(), body)

    def test_partial_http_status_is_rejected(self):
        response = Response(b"only a range")
        response.status = 206
        with mock.patch("ghdl.urllib.request.urlopen", return_value=response):
            with self.assertRaises(OSError):
                ghdl.download_to(RAW, self.dest)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_zip_directory_structure_is_checked_before_publication(self):
        target = RAW.replace("data.bin", "snapshot.zip")
        self.dest.write_bytes(b"original")
        for body in (b"not a zip", b'{"error":"unavailable"}'):
            with self.subTest(body=body), mock.patch("ghdl.urllib.request.urlopen", return_value=Response(body)):
                with self.assertRaises(OSError):
                    ghdl.download_to("https://mirror.invalid/" + target, self.dest, overwrite=True, target_url=target)
            self.assertEqual(self.dest.read_bytes(), b"original")
            self.only_destination()
        body = zip_payload()
        with mock.patch("ghdl.urllib.request.urlopen", return_value=Response(body)):
            ghdl.download_to("https://mirror.invalid/" + target, self.dest, overwrite=True, target_url=target)
        self.assertEqual(self.dest.read_bytes(), body)
        self.only_destination()

    def test_mirror_retry_cleans_partial_before_next_attempt(self):
        calls = []
        def fetch(request, **kwargs):
            calls.append(request.full_url)
            self.assertFalse(self.dest.exists())
            self.assertEqual(list(self.directory.iterdir()), [])
            return Response(b"partial", error_after=True) if len(calls) == 1 else Response(b"complete")
        with mock.patch("ghdl.PROXIES", ["https://a.invalid/", "https://b.invalid/"]), mock.patch("ghdl.urllib.request.urlopen", side_effect=fetch):
            self.assertTrue(ghdl.try_mirrors(RAW, self.dest))
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.dest.read_bytes(), b"complete")
        self.only_destination()

    def test_failed_mirrors_preserve_overwrite_target(self):
        self.dest.write_bytes(b"original")
        with mock.patch("ghdl.PROXIES", ["https://a.invalid/", "https://b.invalid/"]), mock.patch("ghdl.urllib.request.urlopen", side_effect=lambda *a, **kw: Response(b"partial", error_after=True)):
            self.assertFalse(ghdl.try_mirrors(RAW, self.dest, overwrite=True))
        self.assertEqual(self.dest.read_bytes(), b"original")
        self.only_destination()


class URLTests(unittest.TestCase):
    def test_existing_valid_conversions(self):
        cases = {
            "https://github.com/owner/repo": ("repo", "owner", "repo"),
            "http://github.com/owner/repo.git/": ("repo", "owner", "repo.git"),
            "github.com/owner/repo": ("repo", "owner", "repo"),
            "https://github.com/owner/repo/blob/main/dir/file.txt": ("file", "https://raw.githubusercontent.com/owner/repo/main/dir/file.txt"),
            RAW: ("file", RAW),
            "https://github.com/owner/repo/releases/download/v1.0/app.exe": ("file", "https://github.com/owner/repo/releases/download/v1.0/app.exe"),
            "https://github.com/owner/repo/archive/refs/heads/main.zip": ("file", "https://github.com/owner/repo/archive/refs/heads/main.zip"),
            "https://github.com/owner/repo/archive/refs/tags/v1.0.zip": ("file", "https://github.com/owner/repo/archive/refs/tags/v1.0.zip"),
            "https://github.com/owner/repo/archive/abc123.zip": ("file", "https://github.com/owner/repo/archive/abc123.zip"),
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(ghdl.classify(url), expected)

    def test_untrusted_or_unsupported_urls_are_rejected(self):
        urls = [
            "https://evil.invalid/raw.githubusercontent.com/owner/repo/main/x",
            "https://github.com.evil.invalid/owner/repo",
            "https://raw.githubusercontent.com.evil.invalid/owner/repo/main/x",
            "https://user:secret@github.com/owner/repo", "https://github.com@evil.invalid/owner/repo",
            "https://github.com/owner/repo?token=secret", RAW + "?access_token=secret", RAW + "#secret", RAW + "?",
            "ftp://github.com/owner/repo", "https://github.com:444/owner/repo",
            "https://github.com/owner/repo/issues", "https://github.com/owner/repo/tree/main",
            "https://github.com/owner/repo/releases/tag/v1", "https://github.com/owner/repo/archive/main.tar.gz",
            "https://github.com/owner", "https://raw.githubusercontent.com/owner/repo",
            "https://github.com/owner/repo/blob/main", RAW.replace("data.bin", "%2e%2e/private"),
            RAW.replace("data.bin", "%2Fetc%2Fpasswd"), RAW.replace("data.bin", "file\\name"),
            RAW.replace("data.bin", "%252e%252e/private"), RAW.replace("data.bin", "%252Fprivate"),
            RAW.replace("data.bin", "bad\nname"), "https://github.com/owner/..", "https://github.com/owner/repo//blob/main/x",
        ]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                ghdl.classify(url)


class PublicBoundaryTests(unittest.TestCase):
    def run_main(self, args):
        with mock.patch("sys.argv", ["ghdl.py"] + args), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return ghdl.main()

    def test_api_verification_uses_official_host_without_credentials(self):
        response = Response(json.dumps(PUBLIC).encode())
        with mock.patch("ghdl.urllib.request.urlopen", return_value=response) as fetch:
            ghdl.verify_public_repository("owner", "repo")
        request = fetch.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.github.com/repos/owner/repo")
        self.assertFalse(request.has_header("Authorization"))

    def test_private_missing_and_unexpected_api_data_fail_closed(self):
        invalid = [{**PUBLIC, "private": True}, {"private": False}, {**PUBLIC, "visibility": "private"}, {**PUBLIC, "private": 0}, {**PUBLIC, "full_name": "different/project"}, []]
        for data in invalid:
            with self.subTest(data=data), mock.patch("ghdl.urllib.request.urlopen", return_value=Response(json.dumps(data).encode())):
                with self.assertRaises(OSError):
                    ghdl.verify_public_repository("owner", "repo")

    def test_malformed_api_json_is_a_safe_failure(self):
        with mock.patch("ghdl.urllib.request.urlopen", return_value=Response(b"<html>rate limited</html>")):
            with self.assertRaises(OSError):
                ghdl.verify_public_repository("owner", "repo")

    def test_failed_public_verification_never_contacts_mirrors(self):
        for response in [Response(json.dumps({**PUBLIC, "private": True}).encode()), OSError("HTTP 403 or network unavailable")]:
            with self.subTest(response=response), tempfile.TemporaryDirectory() as directory:
                with mock.patch("ghdl.urllib.request.urlopen", side_effect=[response]) as fetch:
                    self.assertNotEqual(self.run_main([RAW, directory]), 0)
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_invalid_url_does_not_start_any_network_request(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("ghdl.urllib.request.urlopen") as fetch:
            self.assertNotEqual(self.run_main([RAW + "?token=secret", directory]), 0)
        fetch.assert_not_called()

    def test_cli_checks_public_once_then_downloads_without_auth(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("ghdl.urllib.request.urlopen", side_effect=[Response(json.dumps(PUBLIC).encode()), Response(b"payload")]) as fetch:
                self.assertEqual(self.run_main([RAW, directory]), 0)
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(Path(directory, "data.bin").read_bytes(), b"payload")
            for call in fetch.call_args_list:
                self.assertFalse(call.args[0].has_header("Authorization"))

    def test_cli_existing_file_stays_untouched_and_overwrite_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory, "data.bin")
            dest.write_bytes(b"original")
            with mock.patch("ghdl.urllib.request.urlopen", return_value=Response(json.dumps(PUBLIC).encode())):
                self.assertNotEqual(self.run_main([RAW, directory]), 0)
            self.assertEqual(dest.read_bytes(), b"original")
            with mock.patch("ghdl.urllib.request.urlopen", side_effect=[Response(json.dumps(PUBLIC).encode()), Response(b"new")]):
                self.assertEqual(self.run_main([RAW, directory, "--overwrite"]), 0)
            self.assertEqual(dest.read_bytes(), b"new")

    def test_root_branch_fallback_verifies_public_only_once(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("ghdl.PROXIES", ["https://mirror.invalid/"]):
            responses = [Response(json.dumps(PUBLIC).encode()), OSError("main not found"), Response(zip_payload())]
            with mock.patch("ghdl.urllib.request.urlopen", side_effect=responses) as fetch:
                self.assertEqual(self.run_main(["https://github.com/owner/repo", directory]), 0)
            urls = [call.args[0].full_url for call in fetch.call_args_list]
            self.assertEqual(len([url for url in urls if url.startswith("https://api.github.com/")]), 1)
            self.assertTrue(urls[1].endswith("/main.zip"))
            self.assertTrue(urls[2].endswith("/master.zip"))
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ["repo-master.zip"])


if __name__ == "__main__":
    unittest.main()
