import tempfile
import unittest
from pathlib import Path

from ai_news_bot.r2 import build_public_url, build_r2_key, create_presigned_get_url, upload_file_to_r2


class FakeS3Client:
    def __init__(self):
        self.calls = []

    def upload_file(self, path, bucket, key, ExtraArgs=None):
        self.calls.append(
            {
                "path": path,
                "bucket": bucket,
                "key": key,
                "extra_args": ExtraArgs,
            }
        )

    def generate_presigned_url(self, operation, Params=None, ExpiresIn=None):
        self.calls.append(
            {
                "operation": operation,
                "params": Params,
                "expires_in": ExpiresIn,
            }
        )
        return "https://signed.example.com/report.html"


class R2Tests(unittest.TestCase):
    def test_build_r2_key_joins_prefix_and_filename(self):
        self.assertEqual(build_r2_key("daily/", "/2026-06-26.md"), "daily/2026-06-26.md")
        self.assertEqual(build_r2_key("", "latest.md"), "latest.md")

    def test_build_public_url_escapes_spaces_but_keeps_slashes(self):
        self.assertEqual(
            build_public_url("https://cdn.example.com/base", "daily/hello world.md"),
            "https://cdn.example.com/base/daily/hello%20world.md",
        )

    def test_upload_file_to_r2_uses_s3_compatible_client(self):
        client = FakeS3Client()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            path.write_text("hello", encoding="utf-8")

            result = upload_file_to_r2(
                path=path,
                bucket="reports",
                key="daily/report.md",
                endpoint_url="https://account.r2.cloudflarestorage.com",
                access_key_id="access",
                secret_access_key="secret",
                public_base_url="https://reports.example.com",
                client=client,
            )

        self.assertEqual(result.bucket, "reports")
        self.assertEqual(result.key, "daily/report.md")
        self.assertEqual(result.url, "https://reports.example.com/daily/report.md")
        self.assertEqual(client.calls[0]["bucket"], "reports")
        self.assertEqual(client.calls[0]["key"], "daily/report.md")
        self.assertEqual(client.calls[0]["extra_args"]["ContentType"], "text/markdown; charset=utf-8")

    def test_create_presigned_get_url_uses_get_object(self):
        client = FakeS3Client()

        url = create_presigned_get_url(
            bucket="reports",
            key="daily/report.html",
            endpoint_url="https://account.r2.cloudflarestorage.com",
            access_key_id="access",
            secret_access_key="secret",
            expires_seconds=3600,
            client=client,
        )

        self.assertEqual(url, "https://signed.example.com/report.html")
        self.assertEqual(client.calls[0]["operation"], "get_object")
        self.assertEqual(client.calls[0]["params"], {"Bucket": "reports", "Key": "daily/report.html"})
        self.assertEqual(client.calls[0]["expires_in"], 3600)


if __name__ == "__main__":
    unittest.main()
