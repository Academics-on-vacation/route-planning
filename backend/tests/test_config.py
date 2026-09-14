import os
import runpy
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "backend" / "app" / "config.py"
    path.parent.mkdir(parents=True)
    shutil.copyfile(Path(__file__).resolve().parents[1] / "app" / "config.py", path)
    (tmp_path / ".env").write_text(
        "POSTGRES_DB=fixture_db\nPOSTGRES_USER=fixture_user\nPOSTGRES_PASSWORD=fixture_password\n"
    )
    (tmp_path / "backend" / ".env").write_text("DB_PASSWORD=obsolete_password\n")
    return path


@pytest.mark.parametrize("directory", [".", "backend", "backend/app"])
def test_config_does_not_read_env_files(config_path, monkeypatch, directory):
    monkeypatch.chdir(config_path.parents[2] / directory)
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValidationError) as error:
            runpy.run_path(str(config_path))
    assert error.value.errors()[0]["type"] == "missing"
    assert error.value.errors()[0]["loc"] == ("DB_PASSWORD",)


@pytest.mark.parametrize("prefix", ["DB", "POSTGRES"])
def test_settings_from_environment(config_path, prefix):
    environment = {
        f"{prefix}_PASSWORD": "environment_password",
        f"{prefix}_USER": "environment_user",
        "DB_NAME" if prefix == "DB" else "POSTGRES_DB": "environment_db",
        "DB_HOST": "postgres",
        "DB_PORT": "5433",
    }
    with patch.dict(os.environ, environment, clear=True):
        settings = runpy.run_path(str(config_path))["settings"]

    assert settings.db_host == "postgres"
    assert settings.db_port == 5433
    assert settings.db_name == "environment_db"
    assert settings.db_user == "environment_user"
    assert settings.db_password == "environment_password"


def test_container_settings_without_env_file(config_path):
    (config_path.parents[2] / ".env").unlink()
    with patch.dict(os.environ, {"DB_PASSWORD": "container_password"}, clear=True):
        settings = runpy.run_path(str(config_path))["settings"]

    assert settings.db_password == "container_password"


def test_db_variables_take_priority_over_postgres_aliases(config_path):
    with patch.dict(
        os.environ,
        {"DB_PASSWORD": "db_password", "POSTGRES_PASSWORD": "postgres_password"},
        clear=True,
    ):
        settings = runpy.run_path(str(config_path))["settings"]

    assert settings.db_password == "db_password"
