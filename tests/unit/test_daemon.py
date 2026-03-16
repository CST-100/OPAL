"""Tests for the daemon lifecycle module."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from opal.daemon import (
    DaemonStatus,
    format_uptime,
    get_daemon_status,
    get_log_file,
    get_pid_file,
    is_process_alive,
    read_pid_file,
    tail_logs,
)


class TestPidFile:
    def test_read_valid_pid_file(self, tmp_path):
        pid_file = tmp_path / "opal.pid"
        pid_file.write_text("12345")
        assert read_pid_file(pid_file) == 12345

    def test_read_missing_pid_file(self, tmp_path):
        pid_file = tmp_path / "opal.pid"
        assert read_pid_file(pid_file) is None

    def test_read_invalid_pid_file(self, tmp_path):
        pid_file = tmp_path / "opal.pid"
        pid_file.write_text("not-a-pid")
        assert read_pid_file(pid_file) is None

    def test_read_empty_pid_file(self, tmp_path):
        pid_file = tmp_path / "opal.pid"
        pid_file.write_text("")
        assert read_pid_file(pid_file) is None

    def test_get_pid_file_path(self, tmp_path):
        assert get_pid_file(tmp_path) == tmp_path / "opal.pid"

    def test_get_log_file_path(self, tmp_path):
        assert get_log_file(tmp_path) == tmp_path / "opal.log"


class TestIsProcessAlive:
    def test_current_process_is_alive(self):
        assert is_process_alive(os.getpid()) is True

    def test_nonexistent_pid(self):
        # Use a very high PID that's unlikely to exist
        assert is_process_alive(999999999) is False

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_permission_error_means_alive(self):
        with patch("os.kill", side_effect=PermissionError):
            assert is_process_alive(1) is True


class TestGetDaemonStatus:
    def test_no_pid_file(self, tmp_path):
        status = get_daemon_status(tmp_path)
        assert status.running is False
        assert status.pid is None

    def test_stale_pid_file_cleaned_up(self, tmp_path):
        pid_file = tmp_path / "opal.pid"
        pid_file.write_text("999999999")

        status = get_daemon_status(tmp_path)
        assert status.running is False
        assert not pid_file.exists()  # stale file cleaned up

    def test_running_process(self, tmp_path):
        pid_file = tmp_path / "opal.pid"
        pid_file.write_text(str(os.getpid()))

        status = get_daemon_status(tmp_path)
        assert status.running is True
        assert status.pid == os.getpid()
        assert status.uptime_seconds is not None
        assert status.uptime_seconds >= 0


class TestTailLogs:
    def test_tail_missing_log_file(self, tmp_path, capsys):
        log_file = tmp_path / "opal.log"
        tail_logs(log_file, lines=10, follow=False)
        captured = capsys.readouterr()
        assert "No log file" in captured.out

    def test_tail_log_file(self, tmp_path, capsys):
        log_file = tmp_path / "opal.log"
        lines = [f"Line {i}\n" for i in range(100)]
        log_file.write_text("".join(lines))

        tail_logs(log_file, lines=5, follow=False)
        captured = capsys.readouterr()
        assert "Line 95" in captured.out
        assert "Line 99" in captured.out
        assert "Line 94" not in captured.out

    def test_tail_fewer_lines_than_requested(self, tmp_path, capsys):
        log_file = tmp_path / "opal.log"
        log_file.write_text("Line 1\nLine 2\n")

        tail_logs(log_file, lines=50, follow=False)
        captured = capsys.readouterr()
        assert "Line 1" in captured.out
        assert "Line 2" in captured.out


class TestFormatUptime:
    def test_none(self):
        assert format_uptime(None) == "unknown"

    def test_seconds(self):
        assert format_uptime(45) == "45s"

    def test_minutes(self):
        assert format_uptime(125) == "2m 05s"

    def test_hours(self):
        assert format_uptime(3661) == "1h 01m 01s"

    def test_zero(self):
        assert format_uptime(0) == "0s"


class TestConfigHelpers:
    def test_config_set_and_read(self, tmp_path):
        """Test config_set writes to opal.env and config_get reads it."""
        from opal.config import config_set, get_config_file

        with patch("opal.config.get_config_file", return_value=tmp_path / "opal.env"):
            config_set("port", "9090")
            content = (tmp_path / "opal.env").read_text()
            assert "OPAL_PORT=9090" in content

    def test_config_set_updates_existing(self, tmp_path):
        """Test config_set updates an existing key."""
        env_file = tmp_path / "opal.env"
        env_file.write_text("OPAL_PORT=8080\nOPAL_HOST=0.0.0.0\n")

        from opal.config import config_set

        with patch("opal.config.get_config_file", return_value=env_file):
            config_set("port", "9090")
            content = env_file.read_text()
            assert "OPAL_PORT=9090" in content
            assert "OPAL_PORT=8080" not in content
            assert "OPAL_HOST=0.0.0.0" in content

    def test_config_show(self):
        """Test config_show returns all settings."""
        from opal.config import config_show

        result = config_show()
        assert "host" in result
        assert "port" in result
        assert "database_url" in result

    def test_config_get_valid_key(self):
        """Test config_get returns a value for valid keys."""
        from opal.config import config_get

        assert config_get("port") is not None

    def test_config_get_invalid_key(self):
        """Test config_get returns None for invalid keys."""
        from opal.config import config_get

        assert config_get("nonexistent_key") is None
