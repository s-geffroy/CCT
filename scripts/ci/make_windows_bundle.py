"""Fabrique le ZIP Windows d'une release et son empreinte SHA-256.

Usage : python3 scripts/ci/make_windows_bundle.py VERSION IMAGE DIGEST DOSSIER_SORTIE

- les lanceurs .cmd a la racine, les scripts PowerShell sous scripts/windows/ ;
- release-manifest.json avec l'image PAR DIGEST (jamais un tag mutable) ;
- le .sha256 est calcule APRES l'archive, publie a cote (pas dedans) ;
- l'archive est relue et controlee avant d'etre declaree bonne.
Le depot doit etre extrait avec les fins de ligne CRLF des .cmd/.ps1
(.gitattributes) : on le verifie ici aussi.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = ROOT / "packaging" / "windows"
LAUNCHERS = ["INSTALLER.cmd", "OUVRIR.cmd", "ARRETER.cmd", "METTRE_A_JOUR.cmd", "SAUVEGARDER.cmd",
             "RESTAURER.cmd", "DESINSTALLER.cmd", "COLLECTER_DIAGNOSTIC.cmd"]
SCRIPTS = ["common.ps1", "verify.ps1", "install.ps1", "start.ps1", "stop.ps1", "update.ps1", "backup.ps1",
           "restore.ps1", "uninstall.ps1", "collect-diagnostic.ps1"]
DOCS = {"README_WINDOWS.md": WINDOWS / "README_WINDOWS.md", "VALIDATION_WINDOWS.md": WINDOWS / "VALIDATION_WINDOWS.md",
        "compose.yaml": WINDOWS / "compose.yaml", "LICENSE": ROOT / "LICENSE",
        "THIRD_PARTY_NOTICES.md": ROOT / "THIRD_PARTY_NOTICES.md"}


def fail(message: str) -> None:
    print(f"ECHEC : {message}", file=sys.stderr)
    sys.exit(1)


def main(version: str, image: str, digest: str, out_dir: Path) -> Path:
    if not re.fullmatch(r"v\d+\.\d+\.\d+([-.][A-Za-z0-9.-]+)?", version):
        fail(f"tag de release invalide : {version}")
    if not re.fullmatch(r"ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+", image):
        fail(f"image GHCR invalide : {image}")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        fail(f"digest invalide : {digest}")

    files: dict[str, bytes] = {}
    for name in LAUNCHERS:
        files[name] = (WINDOWS / name).read_bytes()
    for name in SCRIPTS:
        files[f"scripts/windows/{name}"] = (WINDOWS / name).read_bytes()
    for name, path in DOCS.items():
        files[name] = path.read_bytes()
    for name, data in files.items():
        if name.endswith((".cmd", ".ps1")):
            if any(b > 127 for b in data):
                fail(f"{name} contient des caracteres non ASCII")
            if re.search(rb"(?<!\r)\n", data):
                fail(f"{name} n'a pas des fins de ligne CRLF (checkout sans .gitattributes ?)")
    manifest = {
        "schema_version": 1,
        "app_version": version,
        "target_platform": "linux/amd64",
        "windows_target": "Windows 11 x64 (23H2+) avec Docker Desktop et WSL 2",
        "image_ref": f"{image}@{digest}",
        "host_port_default": 8765,
    }
    files["release-manifest.json"] = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()

    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / f"ChessCalculationTrainer-Windows-{version}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))  # archive reproductible
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, files[name])

    with zipfile.ZipFile(archive) as z:  # relecture : ce qui est publie est ce qui a ete verifie
        names = set(z.namelist())
        needed = {*LAUNCHERS, *(f"scripts/windows/{s}" for s in SCRIPTS), *DOCS, "release-manifest.json"}
        if needed - names:
            fail(f"fichiers absents de l'archive : {sorted(needed - names)}")
        if json.loads(z.read("release-manifest.json"))["image_ref"] != f"{image}@{digest}":
            fail("manifeste incoherent")
        if b":latest" in z.read("release-manifest.json"):
            fail("image :latest interdite")
    digest_zip = hashlib.sha256(archive.read_bytes()).hexdigest()
    (out_dir / f"{archive.name}.sha256").write_text(f"{digest_zip}  {archive.name}\n")
    print(f"{archive.name} : {len(files)} fichiers, sha256 {digest_zip}")
    return archive


if __name__ == "__main__":
    if len(sys.argv) != 5:
        fail("usage : make_windows_bundle.py VERSION IMAGE DIGEST DOSSIER_SORTIE")
    main(sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4]))
