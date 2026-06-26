"""Filesystem Tool 統合テスト。"""
import pytest
from unittest.mock import patch
from pathlib import Path

pytestmark = pytest.mark.integration


@pytest.fixture
def allowed_tmp(tmp_path):
    """許可ディレクトリとして tmp_path を登録したフィクスチャ。"""
    with patch("tools.filesystem.filesystem_tools._ALLOWED_BASE_DIRS", [str(tmp_path)]):
        yield tmp_path


class TestReadFile:
    def test_read_file_success(self, allowed_tmp):
        from tools.filesystem.filesystem_tools import read_file

        f = allowed_tmp / "hello.txt"
        f.write_text("Hello, World!")

        result = read_file.invoke({"file_path": str(f)})
        assert result["success"] is True
        assert result["content"] == "Hello, World!"

    def test_read_file_not_found(self, allowed_tmp):
        from tools.filesystem.filesystem_tools import read_file

        result = read_file.invoke({"file_path": str(allowed_tmp / "nonexistent.txt")})
        assert result["success"] is False

    def test_read_file_blocked_path(self):
        from tools.filesystem.filesystem_tools import read_file

        result = read_file.invoke({"file_path": "/etc/passwd"})
        assert result["success"] is False
        assert "error" in result


class TestSearchFiles:
    def test_search_by_pattern(self, allowed_tmp):
        from tools.filesystem.filesystem_tools import search_files

        (allowed_tmp / "foo.py").write_text("print('hello')")
        (allowed_tmp / "bar.java").write_text("System.out.println('hello');")

        result = search_files.invoke({
            "base_dir": str(allowed_tmp),
            "pattern": "*.py",
        })
        assert result["success"] is True
        assert result["count"] == 1
        assert "foo.py" in result["matches"][0]

    def test_search_by_content(self, allowed_tmp):
        from tools.filesystem.filesystem_tools import search_files

        (allowed_tmp / "a.txt").write_text("TARGET_KEYWORD here")
        (allowed_tmp / "b.txt").write_text("nothing here")

        result = search_files.invoke({
            "base_dir": str(allowed_tmp),
            "pattern": "*.txt",
            "content_keyword": "TARGET_KEYWORD",
        })
        assert result["success"] is True
        assert result["count"] == 1


class TestWriteFile:
    def test_write_file_success(self, allowed_tmp):
        from tools.filesystem.filesystem_tools import write_file

        target = allowed_tmp / "output.txt"
        result = write_file.invoke({
            "file_path": str(target),
            "content": "Written by AI Agent",
        })
        assert result["success"] is True
        assert target.read_text() == "Written by AI Agent"

    def test_write_file_blocked_path(self):
        from tools.filesystem.filesystem_tools import write_file

        result = write_file.invoke({
            "file_path": "/tmp/evil.sh",
            "content": "rm -rf /",
        })
        assert result["success"] is False
