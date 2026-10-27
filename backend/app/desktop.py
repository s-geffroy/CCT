"""Lanceur de bureau (Lot 7) : l'application sans Docker, sur le PC de l'utilisateur.

    python -m app.desktop            demarre (ou rejoint) l'application et ouvre le navigateur
    python -m app.desktop --stop     arrete l'instance en cours (installateur, mise a jour)

- Une seule instance par utilisateur : un verrou sur <donnees>/instance.lock.
  Un second lancement ouvre simplement le navigateur sur l'instance en cours.
- Port local 8765 de preference, sinon un port libre voisin, sinon un port
  choisi par le systeme ; toujours sur 127.0.0.1.
- Arret propre par `POST /api/v1/desktop/shutdown`, protege par un jeton
  aleatoire ecrit dans <donnees>/instance.json (dossier de l'utilisateur).
- Journal dans <donnees>/logs/cct.log (tournant), la console etant absente
  sous `pythonw`.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
import secrets
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import replace
from pathlib import Path

APP_DIR_NAME = "ChessCalculationTrainer"
PREFERRED_PORT = 8765
PORT_ATTEMPTS = 10
TOKEN_HEADER = "X-CCT-Token"
INSTANCE_FILE = "instance.json"
LOCK_FILE = "instance.lock"
JOIN_WAIT_S = 60.0


def default_data_dir(environ: dict[str, str] | None = None, windows: bool | None = None) -> Path:
    environ = os.environ if environ is None else environ
    windows = os.name == "nt" if windows is None else windows
    if environ.get("APP_DATA_DIR"):
        return Path(environ["APP_DATA_DIR"])
    if windows:
        base = environ.get("LOCALAPPDATA") or os.path.join(environ.get("USERPROFILE", "."), "AppData", "Local")
        return Path(base) / APP_DIR_NAME / "data"
    base = environ.get("XDG_DATA_HOME") or os.path.join(environ.get("HOME", "."), ".local", "share")
    return Path(base) / "chess-calculation-trainer"


def default_static_dir() -> Path:
    """`static/` a cote du paquet `app` (installateur Windows comme image Docker)."""
    if os.environ.get("APP_STATIC_DIR"):
        return Path(os.environ["APP_STATIC_DIR"])
    return Path(__file__).resolve().parent.parent / "static"


# ------------------------------------------------------------ instance unique

class InstanceLock:
    """Verrou exclusif tenu pendant toute la vie du processus (libere par le systeme a sa mort)."""

    def __init__(self, path: Path):
        self.path = path
        self._fh = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self._fh = fh
        return True

    def release(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def read_instance(data_dir: Path) -> dict | None:
    try:
        info = json.loads((data_dir / INSTANCE_FILE).read_text(encoding="utf-8"))
        return info if {"port", "token", "pid"} <= set(info) else None
    except (OSError, ValueError):
        return None


def write_instance(data_dir: Path, info: dict) -> None:
    path = data_dir / INSTANCE_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(info), encoding="utf-8")
    if os.name != "nt":
        tmp.chmod(0o600)
    os.replace(tmp, path)


def instance_url(info: dict) -> str:
    return f"http://127.0.0.1:{info['port']}/"


def is_alive(info: dict, timeout: float = 2.0) -> bool:
    """Notre instance repond-elle ? (jeton verifie : pas un autre programme sur ce port)"""
    request = urllib.request.Request(instance_url(info) + "api/v1/desktop/ping", headers={TOKEN_HEADER: info["token"]})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def request_stop(data_dir: Path, timeout: float = 30.0) -> bool:
    """Demande l'arret de l'instance en cours et attend sa fin. Vrai si plus rien ne tourne."""
    info = read_instance(data_dir)
    if info is None or not is_alive(info):
        return True
    request = urllib.request.Request(instance_url(info) + "api/v1/desktop/shutdown", method="POST", data=b"",
                                     headers={TOKEN_HEADER: info["token"]})
    try:
        urllib.request.urlopen(request, timeout=5).close()
    except (OSError, urllib.error.URLError):
        pass
    deadline = time.monotonic() + timeout
    lock = InstanceLock(data_dir / LOCK_FILE)
    while time.monotonic() < deadline:
        if lock.acquire():  # le verrou ne se libere qu'a la mort du processus
            lock.release()
            return True
        time.sleep(0.2)
    return False


# ------------------------------------------------------------ port

def bind_port(preferred: int, attempts: int = PORT_ATTEMPTS) -> socket.socket:
    """Socket ecoute sur 127.0.0.1 : port prefere, ses voisins, sinon port libre du systeme."""
    candidates = [preferred + i for i in range(attempts)] if preferred else []
    for port in [*candidates, 0]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if os.name == "nt":
            # Sans ce drapeau, Windows laisse un second processus ecouter le meme port.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            sock.close()
            if exc.errno in (errno.EADDRINUSE, errno.EACCES) or getattr(exc, "winerror", None) in (10048, 10013):
                continue
            raise
        sock.listen(128)
        return sock
    raise OSError("aucun port local disponible")


# ------------------------------------------------------------ lancement

def _set_version() -> None:
    """Installateur : la version est dans backend/VERSION (l'image Docker la passe par APP_VERSION)."""
    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    if not os.environ.get("APP_VERSION") and version_file.is_file():
        os.environ["APP_VERSION"] = version_file.read_text(encoding="utf-8").strip()


def import_docker_backup(data_dir: Path) -> Path | None:
    """Premier lancement apres le paquet Docker (v0.1.x) : sa derniere sauvegarde
    (<racine>/backups/cct-*.sqlite, faite par SAUVEGARDER.cmd ou la mise a jour) est
    deposee pour la restauration du demarrage, qui la verifie avant de la prendre."""
    from . import backup

    if (data_dir / "app.sqlite").exists():
        return None
    found = sorted((data_dir.parent / "backups").glob("cct-*.sqlite"))
    if not found:
        return None
    incoming = data_dir / backup.RESTORE_DIR / backup.INCOMING
    incoming.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(found[-1], incoming)
    return found[-1]


def _wait_and_open(server, url: str, open_browser: bool) -> None:
    while not server.started and not server.should_exit:
        time.sleep(0.1)
    if server.started and open_browser:
        webbrowser.open(url)


def serve(data_dir: Path, port: int, open_browser: bool) -> int:
    _set_version()
    import uvicorn

    from .log import get_logger, setup_logging
    from .main import create_app
    from .settings import get_settings

    data_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(log_file=data_dir / "logs" / "cct.log")
    log = get_logger("desktop")

    lock = InstanceLock(data_dir / LOCK_FILE)
    if not lock.acquire():
        # Deja lance (ou en train de demarrer) : on rejoint l'instance existante.
        deadline = time.monotonic() + JOIN_WAIT_S
        while time.monotonic() < deadline:
            info = read_instance(data_dir)
            if info and is_alive(info):
                log.info("application deja ouverte : %s", instance_url(info))
                if open_browser:
                    webbrowser.open(instance_url(info))
                return 0
            time.sleep(0.5)
        log.error("une instance tient le verrou mais ne repond pas")
        return 1

    try:
        sock = bind_port(port)
        bound = sock.getsockname()[1]
        if bound != port:
            log.warning("port %d occupe : port %d utilise", port, bound)
        migrated = import_docker_backup(data_dir)
        if migrated is not None:
            log.info("donnees de l'ancienne version Docker reprises : %s", migrated.name)
        token = secrets.token_urlsafe(32)
        settings = replace(get_settings(), data_dir=data_dir, static_dir=default_static_dir(),
                           desktop_token=token, allowed_hosts=["127.0.0.1", "localhost"])
        app = create_app(settings)
        config = uvicorn.Config(app, log_config=None, access_log=False, server_header=False,
                                lifespan="on", timeout_graceful_shutdown=10)
        server = uvicorn.Server(config)
        app.state.request_shutdown = lambda: setattr(server, "should_exit", True)
        info = {"pid": os.getpid(), "port": bound, "token": token}
        write_instance(data_dir, info)
        threading.Thread(target=_wait_and_open, args=(server, instance_url(info), open_browser), daemon=True).start()
        log.info("application ouverte sur %s", instance_url(info))
        server.run(sockets=[sock])
        return 0 if server.started else 1
    finally:
        try:
            (data_dir / INSTANCE_FILE).unlink(missing_ok=True)
        finally:
            lock.release()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cct", description="Chess Calculation Trainer")
    parser.add_argument("--data-dir", type=Path, default=None, help="dossier des donnees")
    parser.add_argument("--port", type=int, default=PREFERRED_PORT, help="port local prefere")
    parser.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur")
    parser.add_argument("--stop", action="store_true", help="arreter l'instance en cours")
    args = parser.parse_args(argv)
    data_dir = args.data_dir or default_data_dir()
    if args.stop:
        return 0 if request_stop(data_dir) else 1
    return serve(data_dir, args.port, not args.no_browser)


if __name__ == "__main__":
    sys.exit(main())
