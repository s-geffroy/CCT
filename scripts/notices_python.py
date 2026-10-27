"""Dependances Python de l'image finale (venv /venv) : nom, version, licence.
Lance dans l'image `tests` : python scripts/notices_python.py (sortie markdown)."""
from importlib import metadata

rows = []
for dist in metadata.distributions(path=["/venv/lib/python3.13/site-packages"]):
    meta = dist.metadata
    lic = meta.get("License-Expression") or ""
    if not lic:
        classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
        lic = ", ".join(classifiers) or (meta.get("License") or "").splitlines()[0] if (meta.get("License") or classifiers) else "?"
    rows.append((meta["Name"].lower(), meta["Version"], lic.strip()[:80] or "?", meta.get("Home-page") or ""))
for name, version, lic, _home in sorted(set(rows)):
    print(f"| {name} | {version} | {lic} |")
