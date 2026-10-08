"""Object storage behind one small interface: local directory for development, S3-compatible for production."""
from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from .config import Settings


def check_key(key: str) -> str:
    parts = PurePosixPath(key).parts
    if not key or key.startswith("/") or "\\" in key or ".." in parts or len(key) > 200:
        raise ValueError("Unsafe storage key.")
    return key


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / check_key(key)).resolve()
        if self.root.resolve() not in path.parents: raise ValueError("Unsafe storage key.")
        return path

    def put_file(self, key: str, source: Path):
        path = self._path(key); path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".part"); shutil.copyfile(source, temp); temp.replace(path)

    def read_bytes(self, key: str) -> bytes:
        try: return self._path(key).read_bytes()
        except FileNotFoundError as exc: raise KeyError(key) from exc

    @contextmanager
    def local_copy(self, key: str):
        """A real file path for libraries that need one. Read-only use: do not modify it."""
        path = self._path(key)
        if not path.is_file(): raise KeyError(key)
        yield path

    def delete(self, key: str):
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


class S3Storage:
    def __init__(self, settings: Settings, client=None):
        if client is None:
            import boto3
            client = boto3.client("s3", endpoint_url=settings.s3_endpoint or None, region_name=settings.s3_region)
        self.client, self.bucket = client, settings.s3_bucket

    def put_file(self, key: str, source: Path):
        self.client.upload_file(str(source), self.bucket, check_key(key))

    def read_bytes(self, key: str) -> bytes:
        try: return self.client.get_object(Bucket=self.bucket, Key=check_key(key))["Body"].read()
        except self.client.exceptions.NoSuchKey as exc: raise KeyError(key) from exc

    @contextmanager
    def local_copy(self, key: str):
        data = self.read_bytes(key)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "document"; path.write_bytes(data); yield path

    def delete(self, key: str):
        self.client.delete_object(Bucket=self.bucket, Key=check_key(key))

    def exists(self, key: str) -> bool:
        try: self.client.head_object(Bucket=self.bucket, Key=check_key(key)); return True
        except Exception: return False


def make_storage(settings: Settings):
    return S3Storage(settings) if settings.storage_backend == "s3" else LocalStorage(settings.data_dir / "files")
