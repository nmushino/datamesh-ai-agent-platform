"""Git Tool 統合テスト。"""
import os
import pytest
from unittest.mock import patch

pytestmark = pytest.mark.integration


class TestGitSearchSource:
    def test_search_source_found(self, tmp_path):
        """キーワードが見つかった場合 matches が返る。"""
        from tools.git.git_tools import git_search_source

        with patch("tools.git.git_tools._validate_repo_path") as mock_validate, \
             patch("tools.git.git_tools._run_git") as mock_run:
            mock_validate.return_value = (True, str(tmp_path))
            mock_run.return_value = (True, "CustomerService.java:42:public Customer register(")
            result = git_search_source.invoke({
                "repo_path": str(tmp_path),
                "keyword": "register",
                "file_pattern": "*.java",
            })

        assert result["success"] is True
        assert result["count"] == 1

    def test_search_source_no_match(self, tmp_path):
        """一致なしの場合は空リストを返す。"""
        from tools.git.git_tools import git_search_source

        with patch("tools.git.git_tools._validate_repo_path") as mock_validate, \
             patch("tools.git.git_tools._run_git") as mock_run:
            mock_validate.return_value = (True, str(tmp_path))
            mock_run.return_value = (False, "did not match any files")
            result = git_search_source.invoke({
                "repo_path": str(tmp_path),
                "keyword": "nonexistent_keyword_xyz",
            })

        assert result["success"] is True
        assert result["count"] == 0

    def test_search_source_blocked_path(self):
        """ホワイトリスト外のパスはアクセス拒否。"""
        from tools.git.git_tools import git_search_source

        result = git_search_source.invoke({
            "repo_path": "/etc",
            "keyword": "password",
        })
        assert result["success"] is False
        assert "error" in result


class TestGitLog:
    def test_git_log_success(self, tmp_path):
        from tools.git.git_tools import git_log

        fake_log = (
            "abc123|Alice|alice@example.com|2026-06-26|feat: add customer tool\n"
            "def456|Bob|bob@example.com|2026-06-25|fix: error handling"
        )
        with patch("tools.git.git_tools._validate_repo_path") as mock_validate, \
             patch("tools.git.git_tools._run_git") as mock_run:
            mock_validate.return_value = (True, str(tmp_path))
            mock_run.return_value = (True, fake_log)
            result = git_log.invoke({"repo_path": str(tmp_path), "max_count": 10})

        assert result["success"] is True
        assert len(result["commits"]) == 2
        assert result["commits"][0]["author"] == "Alice"


class TestGitCreateBranch:
    def test_create_branch_invalid_name(self, tmp_path):
        """無効な文字を含むブランチ名は拒否する。"""
        from tools.git.git_tools import git_create_branch

        with patch("tools.git.git_tools._validate_repo_path") as mock_validate:
            mock_validate.return_value = (True, str(tmp_path))
            result = git_create_branch.invoke({
                "repo_path": str(tmp_path),
                "branch_name": "feat/bad name with spaces",
            })

        assert result["success"] is False

    def test_create_branch_success(self, tmp_path):
        from tools.git.git_tools import git_create_branch

        with patch("tools.git.git_tools._validate_repo_path") as mock_validate, \
             patch("tools.git.git_tools._run_git") as mock_run:
            mock_validate.return_value = (True, str(tmp_path))
            mock_run.return_value = (True, "Switched to a new branch 'feature/add-tool'")
            result = git_create_branch.invoke({
                "repo_path": str(tmp_path),
                "branch_name": "feature/add-tool",
            })

        assert result["success"] is True
