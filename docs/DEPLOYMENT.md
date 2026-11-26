# Deployment and Operations

Target host: **thor128-2** (192.168.0.123). Never deploy to any other machine.

## Layout

| Purpose | Path |
|---|---|
| Production application | `/opt/sceneforge/` |
| Persistent data | `/var/lib/sceneforge/` |
| Configuration | `/opt/sceneforge/.env` (owned by `nmc220`, mode 600) |
| Service unit | `/etc/systemd/system/sceneforge.service` |

The `~/code/SceneForge` repository is a development workspace, not the
production directory.

## First-time host setup

Run once on thor128-2 (as `nmc220`, uses sudo):

```bash
git -C ~/code/SceneForge pull
bash ~/code/SceneForge/scripts/setup_thor128_2.sh
```

Creates the directory trees, Node.js (build only), `.env`, and the systemd
unit. It does not start the service.

## Deploying an update

From thor128 (dev):

```bash
git commit / push as usual
```

On thor128-2:

```bash
git -C ~/code/SceneForge pull
bash ~/code/SceneForge/scripts/deploy.sh
sudo systemctl restart sceneforge
```

`deploy.sh` rsyncs the repo into `/opt/sceneforge` (excluding `.env`,
`node_modules`, `dist`, `.venv`, caches), refreshes the Python venv, and
builds the production frontend. It refuses to run with a dirty tree or on the
wrong host.

## Service management

```bash
sudo systemctl start sceneforge      # start
sudo systemctl stop sceneforge       # stop
sudo systemctl status sceneforge     # status
sudo journalctl -u sceneforge -f     # live logs
sudo systemctl restart sceneforge    # restart
```

The service is enabled at boot, restarts after crashes (`Restart=always`),
runs as `nmc220` (same as `comfyui.service`), and is independent of SSH
sessions. It starts even when ComfyUI is unavailable.

## URLs

- Local: `http://127.0.0.1:8080`
- LAN: `http://192.168.0.123:8080` (or `http://thor128-2:8080` if the name resolves)

Not exposed publicly. ComfyUI remains on port 8188, unchanged.

## Backup and restore

Backups include the SQLite database, assets, generated images, workflow
templates/mappings, and relevant settings, written to
`/var/lib/sceneforge/backups/`. Consistent SQLite backups use
`VACUUM INTO`. Older backups are retained until an explicit retention policy
is configured. Full backup/restore tooling lands in Phase 8.
