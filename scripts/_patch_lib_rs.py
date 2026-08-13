from pathlib import Path

root = Path(__file__).resolve().parents[1]
p = root / "vpin_frontend/vpin-frontend/src-tauri/src/lib.rs"
text = p.read_text(encoding="utf-8")
needle = '"rust-ark" => build_rust_batch(\n                    &client,'
if needle in text:
    text = text.replace(needle, '"rust-ark" => build_rust_batch(\n                    &client2,', 1)
needle2 = '"rust-ec" => build_rust_batch(\n                    &client,'
if needle2 in text:
    text = text.replace(needle2, '"rust-ec" => build_rust_batch(\n                    &client2,', 1)
out = p.with_suffix(".rs.new")
out.write_text(text, encoding="utf-8")
print("wrote", out)
