from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _detect_repo_root() -> Path:
    env = os.environ.get("VPIN_REPO_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "src" / "cnn_networks").is_dir():
            return parent
    return here.parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VPIN_", extra="ignore")

    repo_root: Path = _detect_repo_root()
    data_dir: Path | None = None
    bsgs_table: Path | None = None
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cp_snark_network_default: str = "A"

    @property
    def resolved_data_dir(self) -> Path:
        if self.data_dir:
            return self.data_dir.resolve()
        return (self.repo_root / "vpin-backend" / "data").resolve()

    @property
    def resolved_bsgs_table(self) -> Path:
        if self.bsgs_table:
            return self.bsgs_table.resolve()
        return (self.repo_root / "src" / "Pre_computed_table" / "table.pickle").resolve()

    @property
    def cp_snark_root(self) -> Path:
        return (self.repo_root / "src" / "cp-snark-full").resolve()

    @property
    def server_crypto_root(self) -> Path:
        return (
            self.repo_root / "vpin-backend" / "crates" / "vpin-server-crypto"
        ).resolve()

    @property
    def cnn_networks_dir(self) -> Path:
        return (self.repo_root / "src" / "cnn_networks").resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
