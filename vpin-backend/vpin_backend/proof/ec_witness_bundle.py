"""EC witness bundle loaded from a model training run."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from vpin_backend.inference.ec_schedule import load_paper_proof_counts


@dataclass(frozen=True)
class EcWitnessLayerManifest:
    layer_id: str
    kind: str
    pt_mul_start: int
    pt_mul_end: int
    pt_add_start: int
    pt_add_end: int


@dataclass(frozen=True)
class EcWitnessManifest:
    model_id: str
    mode: str
    total_pt_mul: int
    total_pt_add: int
    layers: tuple[EcWitnessLayerManifest, ...]


@dataclass(frozen=True)
class EcWitnessBundle:
    model_id: str
    run_dir: Path
    root: Path
    total_pt_mul: int
    total_pt_add: int
    manifest: EcWitnessManifest | None = None

    @property
    def point_mult_dir(self) -> Path:
        return self.root / "pointMult"

    @property
    def point_add_dir(self) -> Path:
        return self.root / "pointAdd"

    def validate(self) -> None:
        weight = self.point_mult_dir / "weight.json"
        if not weight.is_file():
            raise FileNotFoundError(f"missing EC witness: {weight}")
        weights = json.loads(weight.read_text(encoding="utf-8"))
        if len(weights) != self.total_pt_mul:
            raise ValueError(
                f"weight.json len {len(weights)} != schedule total_pt_mul {self.total_pt_mul}"
            )
        add_px = self.point_add_dir / "point_add_px_byte.json"
        if add_px.is_file():
            adds = json.loads(add_px.read_text(encoding="utf-8"))
            if len(adds) != self.total_pt_add:
                raise ValueError(
                    f"point_add count {len(adds)} != schedule total_pt_add {self.total_pt_add}"
                )


def load_ec_witness_from_run(run_dir: Path, model_id: str = "A") -> EcWitnessBundle:
    run_dir = run_dir.resolve()
    counts = load_paper_proof_counts(model_id, run_dir=run_dir)
    root = run_dir / "proof_artifacts" / "ec_witness"
    manifest_path = root / "manifest.json"
    manifest: EcWitnessManifest | None = None
    if manifest_path.is_file():
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        layers = tuple(
            EcWitnessLayerManifest(
                layer_id=str(item["layer_id"]),
                kind=str(item["kind"]),
                pt_mul_start=int(item["pt_mul_start"]),
                pt_mul_end=int(item["pt_mul_end"]),
                pt_add_start=int(item.get("pt_add_start", 0)),
                pt_add_end=int(item.get("pt_add_end", 0)),
            )
            for item in raw.get("layers", [])
        )
        manifest = EcWitnessManifest(
            model_id=str(raw.get("model_id", model_id)),
            mode=str(raw.get("mode", "paper_proof")),
            total_pt_mul=int(raw["total_pt_mul"]),
            total_pt_add=int(raw["total_pt_add"]),
            layers=layers,
        )
    bundle = EcWitnessBundle(
        model_id=model_id,
        run_dir=run_dir,
        root=root,
        total_pt_mul=counts.num_pt_mul,
        total_pt_add=counts.num_pt_add,
        manifest=manifest,
    )
    bundle.validate()
    return bundle
