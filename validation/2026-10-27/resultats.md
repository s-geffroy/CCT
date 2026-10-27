==========================================
 Chess Calculation Trainer - Mise a jour
==========================================
Pre-requis verifies : Windows 11 x64, memoire, disque, WSL 2, Docker Desktop (conteneurs Linux), Compose.
-> Sauvegarde de vos donnees avant la mise a jour
ERREUR : docker compose exec -T app python -m app.backup create a echoue : {"ok": false, "reason": "aucune base a sauvegarder"}

Appuyez sur une touche pour continuer...


# Rapport Chess Calculation Trainer - 2026-10-27 19:22:48 +01:00

## Windows
Microsoft Windows 11 Famille 10.0.26200 (build 26200), 64 bits
Processeur : Intel(R) Core(TM) i5-10400F CPU @ 2.90GHz (12 coeurs logiques)
Memoire : 15.9 Go ; langue : fr-FR
PowerShell : 5.1.26100.9711

## WSL
Version WSL : 3.0.3.0

Version du noyau : 6.18.54.1-1

Version WSLg : 1.0.79

Version MSRDC : 1.2.7391

Version direct3D : 1.611.1-81528511

Version de DXCore : 10.0.26100.1-240331-1435.ge-release

Version de Windows : 10.0.26200.9711

## Docker
Etat : linux
Client 29.9.2 / Serveur 29.9.2 (linux/amd64)
Docker Compose version v5.6.1
CPUs 12 ; memoire 8259416064 ; noyau 6.18.54.1-microsoft-standard-WSL2

## Installation
Dossier : <profil>\AppData\Local\ChessCalculationTrainer (existe : True)
{
  "schema_version": 1,
  "app_version": "v0.1.0",
  "target_platform": "linux/amd64",
  "windows_target": "Windows 11 x64 (23H2+) avec Docker Desktop et WSL 2",
  "image_ref": "ghcr.io/s-geffroy/cct@sha256:3747c11497b707b5dd5ae4c10321104b671aaae2173568b8cfd8336e06fa12b6",
  "host_port_default": 8765
}

APP_CPUS=2.0
APP_MEMORY=2g
ENGINE_HASH_MB=128
ENGINE_THREADS=2
HOST_PORT=8765
IMAGE_REF=ghcr.io/s-geffroy/cct@sha256:3747c11497b707b5dd5ae4c10321104b671aaae2173568b8cfd8336e06fa12b6
Sauvegardes : 0
Raccourci bureau : False

## Conteneur
NAME                              IMAGE                                                                                           COMMAND                  SERVICE   CREATED          STATUS                    PORTS
chess-calculation-trainer-app-1   ghcr.io/s-geffroy/cct@sha256:3747c11497b707b5dd5ae4c10321104b671aaae2173568b8cfd8336e06fa12b6   "python -m uvicorn aÔÇª"   app       35 seconds ago   Up 34 seconds (healthy)   127.0.0.1:8765->8000/tcp
Image sha256:d15bb842ac6a607a6d3e5ea479d7c439a64d6470270747e92d83027cbc302a30 ; demarre 2026-10-27T18:22:16.8815507Z ; sante healthy
Volume chess-calculation-trainer-data cree 2026-10-27T18:22:16Z

## Sante et version
/api/v1/health/live -> 200 {"status":"ok"}
/api/v1/health/ready -> 200 {"status":"ready","checks":{"engine":true,"database":true,"data_dir_writable":true}}
/api/v1/meta -> 200 {"app_version":"v0.1.0","python_chess_version":"1.11.2","schema_version":5,"engine":{"name":"Stockfish 19","author":"the Stockfish developers (see AUTHORS file)","threads":2,"hash_mb":128,"build":{"tag":"sf_19","source_sha256":"519b653d0d1ffb96531d982ccbe5c6a19425e8388e0e3c2f70f34b424ab32d76","net":"nn-1a298aa575a0.nnue","net_sha256":"1a298aa575a085434d29027978dc36867fe9c5bcea9376654b7a8eba1e52dfc2","arch":"x86-64-universal","net_embedded":"yes"}},"capabilities":{"variants":["standard"],"multipv_max":20,"target_depth_default":21}}

## Journal (300 dernieres lignes)
app-1  | 2026-10-27T18:22:18+0000 INFO uvicorn.error Started server process [7]
app-1  | 2026-10-27T18:22:18+0000 INFO uvicorn.error Waiting for application startup.
app-1  | 2026-10-27T18:22:18+0000 INFO cct.app demarrage v0.1.0 (donnees /data)
app-1  | 2026-10-27T18:22:18+0000 INFO cct.db migration appliquee : 0001_positions_games
app-1  | 2026-10-27T18:22:18+0000 INFO cct.db migration appliquee : 0002_sessions
app-1  | 2026-10-27T18:22:18+0000 INFO cct.db migration appliquee : 0003_analysis
app-1  | 2026-10-27T18:22:18+0000 INFO cct.db migration appliquee : 0004_reference_tree
app-1  | 2026-10-27T18:22:18+0000 INFO cct.db migration appliquee : 0005_session_go
app-1  | 2026-10-27T18:22:18+0000 INFO cct.app base prete : schema v5, journal wal
app-1  | 2026-10-27T18:22:18+0000 INFO cct.engine moteur demarre : Stockfish 19 (threads=2, hash=128 Mo)
app-1  | 2026-10-27T18:22:18+0000 INFO uvicorn.error Application startup complete.
app-1  | 2026-10-27T18:22:18+0000 INFO uvicorn.error Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
