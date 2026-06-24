"""Cron scanner — parser unit tests (no host access; exercises _parse_lines)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.scanners.cron import CronScanner


class _FakePD:
    def __init__(self, mapping=None):
        self.mapping = mapping or {}

    def get_project_from_path(self, path):
        for prefix, proj in self.mapping.items():
            if path.startswith(prefix):
                return proj
        return "System"


def _scanner(mapping=None):
    return CronScanner("oci", _FakePD(mapping))


def test_parses_standard_user_crontab_line():
    rows = _scanner()._parse_lines(
        "0 3 * * * /usr/bin/backup.sh\n",
        source="crontab:msinha", has_user_field=False, default_user="msinha",
    )
    assert len(rows) == 1
    a = rows[0]
    assert a["category"] == "cron_job"
    assert a["metadata"]["schedule"] == "0 3 * * *"
    assert a["metadata"]["command"] == "/usr/bin/backup.sh"
    assert a["metadata"]["user"] == "msinha"
    assert a["asset_id"].startswith("oci:cron:")


def test_skips_comments_and_env_assignments():
    text = "# a comment\nPATH=/usr/bin\nMAILTO=root\n\n*/5 * * * * echo hi\n"
    rows = _scanner()._parse_lines(text, source="x", has_user_field=False, default_user="root")
    assert len(rows) == 1
    assert rows[0]["metadata"]["schedule"] == "*/5 * * * *"


def test_nickname_schedule():
    rows = _scanner()._parse_lines("@daily /opt/run.sh\n", source="x", has_user_field=False)
    assert rows[0]["metadata"]["schedule"] == "@daily"
    assert rows[0]["metadata"]["command"] == "/opt/run.sh"


def test_system_crontab_has_user_field():
    rows = _scanner()._parse_lines(
        "0 6 * * * root /etc/cron.daily/thing\n", source="/etc/crontab", has_user_field=True,
    )
    a = rows[0]
    assert a["metadata"]["user"] == "root"
    assert a["metadata"]["command"] == "/etc/cron.daily/thing"


def test_project_attribution_by_command_path():
    rows = _scanner({"/home/msinha/projects/openwebui": "openwebui"})._parse_lines(
        "0 2 * * * /home/msinha/projects/openwebui/backup.sh\n", source="x", has_user_field=False,
    )
    assert rows[0]["project"] == "openwebui"


def test_non_cron_lines_ignored():
    rows = _scanner()._parse_lines("run my job every day now\n", source="x", has_user_field=False)
    assert rows == []
