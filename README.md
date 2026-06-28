# BSGS precomputed tables (Git LFS)

| File | Use |
|------|-----|
| `src/Pre_computed_table/table.pickle` | Python backend / vpin-client |
| `vpin-client/tests/fixtures/table.bin` | Rust ahe-server |

Fetch: `git lfs install && git clone -b features-bsgs --depth 1 ...` or checkout this branch and `git lfs pull`.

Regenerate: `scripts/generate-bsgs-pickle.ps1` (pickle) + see docs/环境配置与手动步骤.md (table.bin).
