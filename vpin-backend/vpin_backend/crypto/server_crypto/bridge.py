"""Bridge to vpin-server-crypto Rust CLI (replaces cp-snark-full over time)."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vpin_backend.config import get_settings
from vpin_backend.protocol.messages import ClientChallenge
from vpin_backend.protocol.server_inputs import ProveRequest, SetupRequest

Phase = Literal["setup", "prove-with-challenge"]


@dataclass
class ServerCryptoResult:
    ok: bool
    phase: str
    network: str
    stdout: str
    stderr: str
    artifact_path: Path | None = None
    setup_path: Path | None = None
    summary: dict | None = None


class ServerCryptoBridge:
    def __init__(self, repo_root: Path | None = None) -> None:
        settings = get_settings()
        self.repo_root = repo_root or settings.repo_root
        self.crypto_root = settings.server_crypto_root
        self.workspace_root = self.crypto_root.parent.parent
        self.manifest = self.workspace_root / "Cargo.toml"

    def is_available(self) -> bool:
        return self.manifest.is_file()

    def _crypto_cmd(self, *extra_args: str) -> list[str]:
        exe = self.workspace_root / "target" / "debug" / "vpin-server-crypto.exe"
        if exe.is_file():
            return [str(exe), *extra_args]
        return [
            "cargo",
            "run",
            "--quiet",
            "--manifest-path",
            str(self.manifest),
            "-p",
            "vpin-server-crypto",
            "--",
            *extra_args,
        ]

    def _cargo_bin(self, *extra_args: str) -> subprocess.CompletedProcess[str]:
        cmd = self._crypto_cmd(*extra_args)
        return subprocess.run(
            cmd,
            cwd=str(self.workspace_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )

    def run_setup(self, request: SetupRequest) -> ServerCryptoResult:
        args = ["setup", request.network_id]
        if request.weights_path:
            args.append(str(request.weights_path))
        proc = self._cargo_bin(*args)
        setup_path = (
            self.crypto_root / "artifacts" / request.network_id / "setup.json"
        )
        return self._result(proc, "setup", request.network_id, setup_path=setup_path)

    def run_prove_with_challenge(self, request: ProveRequest) -> ServerCryptoResult:
        if not request.challenge.gamma:
            return ServerCryptoResult(
                ok=False,
                phase="prove-with-challenge",
                network=request.network_id,
                stdout="",
                stderr="missing client gamma — server must not sample γ",
            )
        ch_dir = self.crypto_root / "artifacts" / request.network_id
        ch_dir.mkdir(parents=True, exist_ok=True)
        ch_path = ch_dir / "client_challenge.json"
        ch_path.write_text(
            request.challenge.model_dump_json(indent=2),
            encoding="utf-8",
        )
        args = ["prove-with-challenge", request.network_id, str(ch_path)]
        if request.setup_artifact:
            args.append(str(request.setup_artifact))
        proc = self._cargo_bin(*args)
        artifact = ch_dir / "protocol.json"
        return self._result(proc, "prove-with-challenge", request.network_id, artifact)

    def run_prove_layer(self, network: str) -> ServerCryptoResult:
        settings = get_settings()
        manifest = settings.cp_snark_root / "Cargo.toml"
        cmd = [
            "cargo",
            "run",
            "--quiet",
            "--manifest-path",
            str(manifest),
            "--",
            "prove-layer",
            network,
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(settings.cp_snark_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        artifact = settings.cp_snark_root / "artifacts" / network / "layer_proofs.json"
        return self._result(proc, "prove-layer", network, artifact)

    def run_phase(self, network: str, phase: Phase, challenge: ClientChallenge | None = None) -> ServerCryptoResult:
        if phase == "setup":
            return self.run_setup(SetupRequest(network_id=network))
        if phase == "prove-with-challenge":
            if challenge is None:
                return ServerCryptoResult(
                    ok=False,
                    phase=phase,
                    network=network,
                    stdout="",
                    stderr="challenge required for prove-with-challenge",
                )
            return self.run_prove_with_challenge(
                ProveRequest(session_id="", network_id=network, challenge=challenge)
            )
        return ServerCryptoResult(
            ok=False,
            phase=phase,
            network=network,
            stdout="",
            stderr=f"unknown phase: {phase}",
        )

    def _result(
        self,
        proc: subprocess.CompletedProcess[str],
        phase: str,
        network: str,
        artifact: Path | None = None,
        setup_path: Path | None = None,
    ) -> ServerCryptoResult:
        summary = None
        target = artifact if artifact and artifact.is_file() else setup_path
        if proc.returncode == 0 and target and target.is_file():
            with target.open(encoding="utf-8") as f:
                data = json.load(f)
            if phase == "setup":
                model = data.get("model_commitment", {})
                summary = {
                    "cm_w": model.get("cm_weights", {}).get("point_hex"),
                    "cm_x": data.get("input_commitment", {})
                    .get("cm_public", {})
                    .get("point_hex"),
                    "num_weights": data.get("num_weights"),
                }
            else:
                summary = {
                    "cm_w": data.get("model_commitment", {})
                    .get("cm_weights", {})
                    .get("point_hex"),
                    "cm_x": data.get("input_commitment", {})
                    .get("cm_public", {})
                    .get("point_hex"),
                    "proof_coverage": data.get("proof_coverage"),
                    "prove_ms": data.get("prove_time_ms"),
                }
        return ServerCryptoResult(
            ok=proc.returncode == 0,
            phase=phase,
            network=network,
            stdout=proc.stdout,
            stderr=proc.stderr,
            artifact_path=artifact if artifact and artifact.is_file() else None,
            setup_path=setup_path if setup_path and setup_path.is_file() else None,
            summary=summary,
        )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="vPIN server-crypto bridge")
    parser.add_argument("--network", default="A")
    parser.add_argument(
        "--phase",
        choices=["setup", "prove-with-challenge"],
        default="setup",
    )
    parser.add_argument("--challenge-json", type=Path, default=None)
    args = parser.parse_args()
    bridge = ServerCryptoBridge()
    if not bridge.is_available():
        print("vpin-server-crypto not found", file=sys.stderr)
        sys.exit(1)
    challenge = None
    if args.challenge_json:
        challenge = ClientChallenge.model_validate_json(
            args.challenge_json.read_text(encoding="utf-8")
        )
    r = bridge.run_phase(args.network, args.phase, challenge=challenge)
    print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    if r.summary:
        print(json.dumps(r.summary, indent=2))
    sys.exit(0 if r.ok else 1)


if __name__ == "__main__":
    main()
