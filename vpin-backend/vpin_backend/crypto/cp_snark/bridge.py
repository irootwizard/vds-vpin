"""
Bridge to src/cp-snark-full (Rust) — **computation proof path**.

Use for trained run_dir witness + paper_proof EC schedule (n₂ = q₁ curve embed).
AHE inference remains separate; do not use vpin-server-crypto for Network A proof.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vpin_backend.config import get_settings

Phase = Literal[
    "setup",
    "full",
    "verify",
    "prove",
    "sample-challenge",
    "prove-with-challenge",
    "verify-file",
    "r4",
]


@dataclass
class CpSnarkResult:
    ok: bool
    phase: str
    network: str
    stdout: str
    stderr: str
    artifact_path: Path | None = None
    challenge_path: Path | None = None
    summary: dict | None = None


def _challenge_json_for_rust(challenge: object) -> str:
    """cp-snark-full expects num_point_adds / num_point_mults (Rust serde names)."""
    data = {
        "gamma": challenge.gamma,
        "gamma_add": challenge.gamma_add,
        "gamma_mult": challenge.gamma_mult,
        "num_point_adds": challenge.num_pt_add,
        "num_point_mults": challenge.num_pt_mult,
    }
    return json.dumps(data, indent=2)


class CpSnarkBridge:
    """cp-snark-full CLI bridge for trained Network A computation proof."""
    def __init__(self, repo_root: Path | None = None) -> None:
        settings = get_settings()
        self.repo_root = repo_root or settings.repo_root
        self.cp_snark_root = settings.cp_snark_root
        self.manifest = self.cp_snark_root / "Cargo.toml"

    def is_available(self) -> bool:
        return self.manifest.is_file()

    def _cargo(self, *extra_args: str) -> subprocess.CompletedProcess[str]:
        cmd = [
            "cargo",
            "run",
            "--quiet",
            "--manifest-path",
            str(self.manifest),
            "--",
            *extra_args,
        ]
        return subprocess.run(
            cmd,
            cwd=str(self.cp_snark_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )

    def run_phase(self, network: str, phase: Phase) -> CpSnarkResult:
        if phase == "sample-challenge":
            proc = self._cargo("sample-challenge", network)
            challenge_path = None
            if proc.returncode == 0 and proc.stdout.strip():
                tmp = self.cp_snark_root / "artifacts" / network / "client_challenge.json"
                tmp.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_text(proc.stdout, encoding="utf-8")
                challenge_path = tmp
            return CpSnarkResult(
                ok=proc.returncode == 0,
                phase=phase,
                network=network,
                stdout=proc.stdout,
                stderr=proc.stderr,
                challenge_path=challenge_path,
            )

        if phase == "prove-with-challenge":
            ch_path = self.cp_snark_root / "artifacts" / network / "client_challenge.json"
            if not ch_path.is_file():
                return CpSnarkResult(
                    ok=False,
                    phase=phase,
                    network=network,
                    stdout="",
                    stderr="missing client_challenge.json — run sample-challenge first",
                )
            proc = self._cargo("prove-with-challenge", network, str(ch_path))
            artifact = self.cp_snark_root / "artifacts" / network / "protocol.json"
            return self._result(proc, phase, network, artifact)

        if phase == "verify-file":
            artifact = self.cp_snark_root / "artifacts" / network / "protocol.json"
            if not artifact.is_file():
                return CpSnarkResult(
                    ok=False,
                    phase=phase,
                    network=network,
                    stdout="",
                    stderr=f"missing {artifact}",
                )
            proc = self._cargo("verify-file", str(artifact))
            return CpSnarkResult(
                ok=proc.returncode == 0,
                phase=phase,
                network=network,
                stdout=proc.stdout,
                stderr=proc.stderr,
                artifact_path=artifact,
            )

        if phase == "r4":
            steps = ("sample-challenge", "prove-with-challenge", "verify-file")
            last: CpSnarkResult | None = None
            for step in steps:
                last = self.run_phase(network, step)  # type: ignore[arg-type]
                if not last.ok:
                    return last
            assert last is not None
            return last

        subcmd = "full" if phase == "prove" else phase
        proc = self._cargo(subcmd, network)
        artifact = self.cp_snark_root / "artifacts" / network / "protocol.json"
        return self._result(proc, subcmd, network, artifact)

    def _result(
        self,
        proc: subprocess.CompletedProcess[str],
        phase: str,
        network: str,
        artifact: Path,
    ) -> CpSnarkResult:
        summary = None
        if proc.returncode == 0 and artifact.is_file():
            with artifact.open(encoding="utf-8") as f:
                data = json.load(f)
            summary = {
                "cm_w": data.get("model_commitment", {})
                .get("cm_weights", {})
                .get("point_hex"),
                "cm_x": data.get("input_commitment", {})
                .get("cm_public", {})
                .get("point_hex"),
                "proof_coverage": data.get("proof_coverage"),
                "l1_binding_ok": data.get("l1_binding_ok"),
                "num_weights": data.get("model_commitment", {}).get("num_weights"),
                "prove_ms": data.get("prove_time_ms"),
                "verify_ms": data.get("verify_time_ms"),
                "has_model_opening": data.get("model_opening") is not None,
            }
        return CpSnarkResult(
            ok=proc.returncode == 0,
            phase=phase,
            network=network,
            stdout=proc.stdout,
            stderr=proc.stderr,
            artifact_path=artifact if artifact.is_file() else None,
            summary=summary,
        )

    def run_full_protocol(self, network: str) -> list[CpSnarkResult]:
        """Legacy same-process demo."""
        results: list[CpSnarkResult] = []
        for phase in ("setup", "full", "verify"):
            r = self.run_phase(network, phase)  # type: ignore[arg-type]
            results.append(r)
            if not r.ok:
                break
        return results

    def run_r4_protocol(self, network: str) -> CpSnarkResult:
        """Cross-process compliant: client γ → server prove → client verify-file."""
        return self.run_phase(network, "r4")

    def run_prove_with_challenge(self, request: "ProveRequest") -> CpSnarkResult:
        """Prove with client γ using trained run_dir witness (cp-snark-full)."""
        from vpin_backend.protocol.server_inputs import ProveRequest as PR

        assert isinstance(request, PR)
        if not request.challenge.gamma:
            return CpSnarkResult(
                ok=False,
                phase="prove-with-challenge",
                network=request.network_id,
                stdout="",
                stderr="missing client gamma",
            )

        import os

        from vpin_backend.proof.registry import load_proof_plan, resolve_run_dir

        model_id = request.model_id or request.network_id
        try:
            run_dir = resolve_run_dir(model_id, request.run_dir)
            plan = load_proof_plan(
                model_id,
                run_dir=run_dir,
                schedule_mode=request.schedule_mode,
            )
        except (KeyError, FileNotFoundError, ValueError) as exc:
            return CpSnarkResult(
                ok=False,
                phase="prove-with-challenge",
                network=request.network_id,
                stdout="",
                stderr=str(exc),
            )

        env = os.environ.copy()
        env["VPIN_RUN_DIR"] = str(plan.run_dir)
        env["VPIN_EC_WITNESS_ROOT"] = str(plan.witness.root)
        env["VPIN_TRACE_ROOT"] = str(plan.run_dir / "proof_artifacts")

        ch_dir = self.cp_snark_root / "artifacts" / request.network_id
        ch_dir.mkdir(parents=True, exist_ok=True)
        ch_path = ch_dir / "client_challenge.json"
        ch_path.write_text(
            _challenge_json_for_rust(request.challenge),
            encoding="utf-8",
        )

        cmd = [
            "cargo",
            "run",
            "--quiet",
            "--manifest-path",
            str(self.manifest),
            "--",
            "prove-with-challenge",
            request.network_id,
            str(ch_path),
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(self.cp_snark_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            env=env,
        )
        artifact = self.cp_snark_root / "artifacts" / request.network_id / "protocol.json"
        return self._result(proc, "prove-with-challenge", request.network_id, artifact)

    def verify_artifact(self, artifact_path: Path) -> CpSnarkResult:
        proc = self._cargo("verify-file", str(artifact_path))
        return CpSnarkResult(
            ok=proc.returncode == 0,
            phase="verify-file",
            network=artifact_path.parent.name,
            stdout=proc.stdout,
            stderr=proc.stderr,
            artifact_path=artifact_path if artifact_path.is_file() else None,
        )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="vPIN CP-SNARK bridge")
    parser.add_argument("--network", default="A")
    parser.add_argument(
        "--phase",
        choices=[
            "setup",
            "full",
            "verify",
            "prove",
            "all",
            "sample-challenge",
            "prove-with-challenge",
            "verify-file",
            "r4",
        ],
        default="all",
    )
    args = parser.parse_args()
    bridge = CpSnarkBridge()
    if not bridge.is_available():
        print("cp-snark-full not found", file=sys.stderr)
        sys.exit(1)
    if args.phase == "all":
        results = bridge.run_full_protocol(args.network)
        for r in results:
            print(f"[{r.phase}] ok={r.ok}")
            if r.summary:
                print(json.dumps(r.summary, indent=2))
        sys.exit(0 if all(r.ok for r in results) else 1)
    if args.phase == "r4":
        r = bridge.run_r4_protocol(args.network)
        print(r.stdout)
        if r.stderr:
            print(r.stderr, file=sys.stderr)
        if r.summary:
            print(json.dumps(r.summary, indent=2))
        sys.exit(0 if r.ok else 1)
    r = bridge.run_phase(args.network, args.phase)  # type: ignore[arg-type]
    print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    sys.exit(0 if r.ok else 1)


if __name__ == "__main__":
    main()
