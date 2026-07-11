#!/usr/bin/env python3
"""Orchestrates the full platform-up sequence with persisted resume state.

Replaces manually re-typing START_AT/STOP_AFTER after a failure: each
successful step is recorded in .bootstrap-state.json (with its duration),
and the next run resumes automatically at the first step that hasn't
completed yet.

An "already completed" step is not blindly trusted: before skipping it, its
convergence check (see platform_checks.py) verifies that the state it
produced still holds — boxes still registered, cluster still reachable,
secret still present, PAT still valid. The first stale step becomes the new
resume point, which makes `make platform-up` a reconciliation command, not
just a crash-resume. Use --no-verify to fall back to trusting the saved
state as-is.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import platform_checks as pc

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / ".bootstrap-state.json"


def check_platform_verify(values: dict[str, str]) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "platform-verify.py"), "--quiet"],
        cwd=ROOT, capture_output=True, text=True,
    )
    summary = (result.stdout.strip().splitlines() or ["pas de sortie"])[-1]
    return result.returncode == 0, summary


# (step name, make target in this repo's Makefile, convergence check)
STEPS: list[tuple[str, str, object]] = [
    ("vm-images", "vm-images", pc.check_vm_images),
    ("cluster-from-images", "cluster-from-images", pc.check_cluster),
    ("snapshot-cluster", "snapshot-cluster", pc.check_vm_snapshot),
    ("platform-bootstrap", "platform-bootstrap", pc.check_argocd_ready),
    ("gitlab-tf-state-seed", "gitlab-tf-state-seed", pc.check_gitlab_tf_state_seeded),
    ("ghcr-pull-secret", "ghcr-pull-secret-wait", pc.check_ghcr_secret),
    ("gitlab-git-creds", "gitlab-git-credentials", pc.check_git_creds),
    ("gitlab-projects", "gitlab-projects-wait", pc.check_gitlab_iac),
    ("argocd-apps", "argocd-apps-wait", pc.check_apps_synced),
    ("platform-verify", "platform-verify", check_platform_verify),
]
STEP_NAMES = [name for name, _, _ in STEPS]


def config_hash(config: str) -> str:
    return hashlib.sha256(pc.config_path(config).read_bytes()).hexdigest()


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"config_hash": "", "completed": [], "steps": {}}
    try:
        state = json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"config_hash": "", "completed": [], "steps": {}}
    state.setdefault("completed", [])
    state.setdefault("steps", {})
    return state


def save_state(state: dict) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def step_index(name: str) -> int:
    if name not in STEP_NAMES:
        sys.exit(f"Etape inconnue: {name}. Etapes valides: {', '.join(STEP_NAMES)}")
    return STEP_NAMES.index(name)


def fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    if seconds >= 60:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds}s"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.environ.get("CONFIG", "platform.yml"))
    parser.add_argument("--make", default=os.environ.get("MAKE_BIN", "make"))
    parser.add_argument("--from", dest="from_step", default="",
                         help="Force la reprise a partir de cette etape (ignore l'etat sauvegarde)")
    parser.add_argument("--to", dest="to_step", default="", help="Arrete apres cette etape")
    parser.add_argument("--no-verify", action="store_true",
                         help="Ne pas verifier la convergence des etapes deja terminees avant de les sauter")
    parser.add_argument("--platform-start-at", default="",
                         help="Transmis en START_AT a l'etape platform-bootstrap (reprise fine dans platform-bootstrap)")
    parser.add_argument("--platform-stop-after", default="",
                         help="Transmis en STOP_AFTER a l'etape platform-bootstrap")
    parser.add_argument("--list", action="store_true", help="Affiche les etapes et leur etat, sans rien executer")
    parser.add_argument("--reset", action="store_true", help="Efface l'etat sauvegarde avant de lancer")
    args = parser.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()

    state = load_state()
    current_hash = config_hash(args.config)
    if state.get("config_hash") != current_hash:
        if state.get("completed"):
            print("==> bootstrap: platform.yml a change depuis la derniere execution, etat sauvegarde ignore.")
        state = {"config_hash": current_hash, "completed": [], "steps": {}}

    if args.list:
        completed = set(state["completed"])
        for name in STEP_NAMES:
            mark = "x" if name in completed else " "
            duration = fmt_duration(state["steps"].get(name, {}).get("duration_seconds"))
            print(f"[{mark}] {name:<22} {duration:>8}")
        return

    values = pc.load_values(args.config)

    if args.from_step:
        start_idx = step_index(args.from_step)
    else:
        start_idx = 0
        for name in state["completed"]:
            if name in STEP_NAMES:
                start_idx = max(start_idx, STEP_NAMES.index(name) + 1)

        # Verifie que les etapes deja terminees le sont toujours : la premiere
        # dont le check echoue devient le nouveau point de reprise.
        if not args.no_verify and start_idx > 0:
            for idx, (name, _, check) in enumerate(STEPS[:start_idx]):
                ok, detail = check(values)
                if not ok:
                    print(f"==> bootstrap: etape '{name}' marquee terminee mais non convergente ({detail}), reprise ici.")
                    start_idx = idx
                    break
                print(f"==> bootstrap: '{name}' verifie — {detail}")

    end_idx = step_index(args.to_step) if args.to_step else len(STEP_NAMES) - 1
    steps_to_run = STEPS[start_idx:end_idx + 1]

    if not steps_to_run:
        print("==> bootstrap: rien a faire (toutes les etapes demandees sont deja terminees et convergentes).")
        return

    print("Bootstrap steps:", " -> ".join(name for name, _, _ in steps_to_run))

    completed = STEP_NAMES[:start_idx]
    state["completed"] = completed
    save_state(state)

    run_started = time.monotonic()
    for name, target, _ in steps_to_run:
        print(f"==> bootstrap-step: {name}")
        cmd = [args.make, target, f"CONFIG={args.config}"]
        if name == "platform-bootstrap":
            if args.platform_start_at:
                cmd.append(f"START_AT={args.platform_start_at}")
            if args.platform_stop_after:
                cmd.append(f"STOP_AFTER={args.platform_stop_after}")
        step_started = time.monotonic()
        try:
            subprocess.run(cmd, check=True, cwd=ROOT)
        except subprocess.CalledProcessError:
            duration = time.monotonic() - step_started
            print(f"\n==> bootstrap: l'etape '{name}' a echoue apres {fmt_duration(duration)}.", file=sys.stderr)
            print(f"    Corrigez le probleme puis relancez la meme commande : "
                  f"elle reprendra automatiquement a '{name}'.", file=sys.stderr)
            sys.exit(1)
        duration = time.monotonic() - step_started
        completed.append(name)
        state["completed"] = completed
        state["steps"][name] = {
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration, 1),
        }
        save_state(state)

    print("\n==> bootstrap: termine. Recapitulatif :")
    for name in STEP_NAMES[:end_idx + 1]:
        duration = fmt_duration(state["steps"].get(name, {}).get("duration_seconds"))
        status = "execute" if name in [n for n, _, _ in steps_to_run] else "deja fait"
        print(f"    {name:<22} {duration:>8}  ({status})")
    print(f"    {'total (cette execution)':<22} {fmt_duration(time.monotonic() - run_started):>8}")


if __name__ == "__main__":
    main()
