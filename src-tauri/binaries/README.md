# Sidecar-Binaries

Dieser Ordner nimmt die von `build_sidecar.py` erzeugten Backend-Binaries auf,
benannt nach Tauris Schema:

    privacy-agent-backend-<target-triple>[.exe]

Beispiele:
- `privacy-agent-backend-x86_64-pc-windows-msvc.exe`
- `privacy-agent-backend-aarch64-apple-darwin`
- `privacy-agent-backend-x86_64-unknown-linux-gnu`

Die Binaries werden **nicht** eingecheckt (siehe .gitignore). Erzeuge sie auf
jeder Zielplattform mit:

    python build_sidecar.py
