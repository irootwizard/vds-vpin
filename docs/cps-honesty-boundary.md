# CPS Honesty Boundary

> Phase Z.11 freezes what the current implementation may claim. It separates
> toy CPS coverage from the still-open Network A and paper-level claims.

## Claim Levels

| Level | Current status | What may be claimed |
|-------|----------------|---------------------|
| EC gadget SNARK | Implemented for PtAdd / PtMul artifacts | EC sub-circuit witnesses verify under the exported challenge and setup. |
| Layer scalar checks | Implemented for toy and Python client checks | Conv / pool / fc arithmetic identities hold for the supplied traces. |
| Spartan PC `cm_W` | Implemented for toy and Network A commitment smoke tests | `W*` is committed by the Phase Z Spartan polynomial commitment surface. |
| L1 model binding | Implemented for toy layout only | Toy trace parameters are linked to toy `W*` slots. |
| Unified CPS.Ver over toy | Implemented as toy-only flow | Toy `cm_W`, layer pi bytes, L1 binding, scalar checks, and replay guard are checked together. |
| Network A CPS.Ver | Not implemented | Do not claim Network A layer pi, L1 binding, or cm_W are all in one verified transcript. |
| Paper-level vPIN end-to-end theorem | Not implemented | Do not claim full privacy-preserving verifiable inference as a production theorem. |

## `proof_coverage` Enum

| Value | Meaning | Claim boundary |
|-------|---------|----------------|
| `skeleton_ec_stub` | Server-crypto placeholder | No real EC proof is wired. |
| `ec_gadget_only` | EC PtAdd / PtMul SNARK path only | No MAC/RLC or model-binding claim. |
| `ec_plus_scalar_check` | EC plus client gamma scalar checks | Scalar checks are not in-circuit MAC proofs. |
| `ec_plus_l1_binding` | EC plus L1 weight binding in R1CS | Only valid when the specific artifact includes L1 binding constraints. |
| `layer_proofs_partial` | Per-layer pi work in progress | Partial layer proof surface; not unified CPS.Ver. |
| `ec_plus_layer_pi_with_model_binding` | Toy CPS flow with Spartan PC `cm_W`, layer pi bytes, and L1 toy model binding | **Toy only.** This is not a Network A or paper-level claim. |
| `cps_ver_unified` | Future M-B' target | Reserved until a non-toy unified verifier is wired and tested. |

The A-prime Merkle module is intentionally absent from this enum. In Phase Z.10
it is only a non-live stub and does not participate in proof generation,
verification, or transcript binding.

## What We Can Claim Today

The toy CPS path may claim `ec_plus_layer_pi_with_model_binding` because it
checks a toy Spartan PC `cm_W`, toy L1 layout binding, per-layer proof bytes, M1
scalar identities, and gamma replay rejection in one client-facing report.

Network A may claim only the parts individually measured in Phase Z:
`cps_comm_w_star` can commit its 1219-element `W*`, and the EC proof path can
prove PtAdd / PtMul artifacts. Those two facts are not yet composed into one
Network A CPS verifier.

## What We Cannot Claim

Do not claim that Network A has `ec_plus_layer_pi_with_model_binding` until the
Network A layer circuits, L1 layout from `j_to_wstar_index.json`, and Spartan PC
`cm_W` are verified in a single transcript.

Do not claim A-prime Merkle model binding. The Z.10 Merkle code only fixes a
4-leaf SHA-256 stub surface for future work.

Do not claim production Poseidon/Ristretto Merkle verification, production setup
ceremony soundness, or paper-level end-to-end vPIN security from the current
toy flow.

## Evidence Anchors

| Evidence | Location |
|----------|----------|
| Toy client CPS coverage return | `vpin-client/vpin_client/verify/cps.py` |
| Backend disclosure mapping | `vpin-backend/vpin_backend/crypto/server_crypto/coverage.py` |
| Protocol message coverage literal | `vpin-backend/vpin_backend/protocol/messages.py` |
| Z.9 Network A performance data | `vpin-backend/tests/perf/Z-9.json` |
| A-prime non-live stub | `src/cp-snark-full/src/commit/merkle.rs` |
