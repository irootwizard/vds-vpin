"""CLI entry for vpin-client."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from vpin_client.crypto.challenge import sample_challenge
from vpin_client.pipeline import InferenceJob, run_ahe_inference, run_mnist_batch


async def _cmd_ahe_infer(args: argparse.Namespace) -> int:
    job = InferenceJob(
        model_id=args.model,
        backend_ws=args.backend,
        mnist_index=args.mnist_index,
        upload_id=args.upload_id,
        image_path=args.image,
        fixed_npy=args.fixed_npy,
    )
    result = await run_ahe_inference(job)
    payload = result.to_dict()

    if args.timing or args.trace:
        if not args.trace and "trace" in payload:
            payload.pop("trace", None)
        print(json.dumps(payload, indent=2))
    else:
        print(f"prediction={result.prediction} label={result.label}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


async def _cmd_eval_mnist(args: argparse.Namespace) -> int:
    def on_progress(phase: str, data: dict) -> None:
        if phase != "batch_item" or not args.progress:
            return
        print(
            f"[ {data['index'] + 1:3d}/{data['limit']} ] correct={data['correct']} "
            f"acc={100.0 * data['accuracy']:.1f}% "
            f"elapsed={data['elapsed_s']:.1f}s eta={data['eta_s']:.1f}s",
            flush=True,
        )

    report = await run_mnist_batch(
        model_id=args.model,
        backend_ws=args.backend,
        limit=args.limit,
        on_progress=on_progress,
    )
    out_dir = Path("reports")
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"batch_{args.limit}_{ts}.json"
    out_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vpin-client", description="vPIN client tools")
    sub = parser.add_subparsers(dest="cmd")

    ch = sub.add_parser("sample-challenge", help="Sample P4 ClientChallenge (CSPRNG)")
    ch.add_argument("--num-pt-add", type=int, default=0)
    ch.add_argument("--num-pt-mult", type=int, default=0)

    infer = sub.add_parser("ahe-infer", help="Run pure AHE inference over WebSocket")
    infer.add_argument("--backend", default="ws://127.0.0.1:8000/api/v1/session/ws")
    infer.add_argument("--model", default="cnn-mnist")
    infer.add_argument("--mnist-index", type=int, default=None)
    infer.add_argument("--upload-id", default=None)
    infer.add_argument("--image", default=None)
    infer.add_argument("--fixed-npy", default=None)
    infer.add_argument("--timing", action="store_true")
    infer.add_argument("--trace", action="store_true", help="Include per-phase inference trace in JSON output")
    infer.add_argument("--json-out", default=None)

    ev = sub.add_parser("eval-mnist-ahe", help="Batch MNIST AHE evaluation")
    ev.add_argument("--backend", default="ws://127.0.0.1:8000/api/v1/session/ws")
    ev.add_argument("--model", default="cnn-mnist")
    ev.add_argument("--limit", type=int, default=50)
    ev.add_argument("--progress", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "sample-challenge":
        c = sample_challenge(args.num_pt_add, args.num_pt_mult)
        print(
            json.dumps(
                {
                    "gamma": c.gamma,
                    "gamma_add": c.gamma_add,
                    "gamma_mult": c.gamma_mult,
                    "num_pt_add": c.num_pt_add,
                    "num_pt_mult": c.num_pt_mult,
                },
                indent=2,
            )
        )
        return 0
    if args.cmd == "ahe-infer":
        return asyncio.run(_cmd_ahe_infer(args))
    if args.cmd == "eval-mnist-ahe":
        return asyncio.run(_cmd_eval_mnist(args))

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
