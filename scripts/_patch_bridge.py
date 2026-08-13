from pathlib import Path

p = Path(__file__).resolve().parents[1] / "vpin-backend/vpin_backend/crypto/server_crypto/bridge.py"
text = p.read_text(encoding="utf-8")
old_init = """        self.crypto_root = settings.server_crypto_root
        self.workspace_root = self.crypto_root.parent.parent
        self.manifest = self.workspace_root / "Cargo.toml\""""
new_init = """        self.crypto_root = settings.server_crypto_root
        self.manifest = self.crypto_root / "Cargo.toml\""""
if old_init in text:
    text = text.replace(old_init, new_init)
text = text.replace("self.workspace_root / ", "self.crypto_root / ")
text = text.replace(
    '            str(self.manifest),\n            "-p",\n            "vpin-server-crypto",\n            "--",',
    '            str(self.manifest),\n            "--",',
)
text = text.replace("cwd=str(self.workspace_root)", "cwd=str(self.crypto_root)")
p.write_text(text, encoding="utf-8")
print("patched", p)
