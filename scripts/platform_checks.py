"""Chargement de platform.yml et checks de convergence partagés.

Utilisé par export-env.py (config seule), bootstrap.py (checks par étape),
platform-verify.py (smoke test de bout en bout) et gitlab-git-creds.py
(validation du PAT existant). Chaque check retourne (ok, détail) sans rien
imprimer : l'appelant décide du format d'affichage.
"""
from __future__ import annotations

import base64
import json
import os
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "platform.yml"

KUBECTL_TIMEOUT = 15  # secondes, par appel


def config_path(config: str | os.PathLike | None = None) -> Path:
    path = Path(config or os.environ.get("CONFIG", DEFAULT_CONFIG))
    return path if path.is_absolute() else ROOT / path


def load_values(config: str | os.PathLike | None = None) -> dict[str, str]:
    with config_path(config).open() as f:
        data = yaml.safe_load(f) or {}

    platform = data["platform"]
    versions = data["versions"]
    repos = platform["repositories"]

    return {
        "GITLAB_DOMAIN": platform["domain"],
        "GITLAB_NAMESPACE": platform["gitlab"]["namespace"],
        "INTERNAL_GITLAB_HOST": platform["gitlab"]["internalHost"],
        "ARGOCD_NAMESPACE": platform["argocd"]["namespace"],
        "ARGOCD_VERSION": versions["argocd"],
        "INFRASTRUCTURE_REPO": repos["infrastructure"],
        "PLATFORM_REPO_ROOT": repos["platform"],
        "GITOPS_REPO_ROOT": repos["gitops"],
        "TOOLBOX_REPO": repos["toolbox"],
    }


def repo_path(values: dict[str, str], key: str) -> Path:
    path = Path(values[key])
    return path if path.is_absolute() else ROOT / path


# ---------------------------------------------------------------------------
# Primitives (kubectl, git credential, API GitLab)
# ---------------------------------------------------------------------------

def _insecure_ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def run_out(cmd: list[str], timeout: int = KUBECTL_TIMEOUT, **kwargs) -> str | None:
    """Retourne stdout si la commande réussit, None sinon (échec ou timeout)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    return result.stdout if result.returncode == 0 else None


def kubectl_out(args: list[str]) -> str | None:
    return run_out(["kubectl", f"--request-timeout={KUBECTL_TIMEOUT - 5}s", *args])


def credential_fill(internal_host: str) -> str:
    """Retourne le mot de passe stocké dans git-credential pour l'hôte interne, '' si absent."""
    out = run_out(
        ["git", "credential", "fill"],
        input=f"protocol=http\nhost={internal_host}\n\n",
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "true"},
    )
    for line in (out or "").splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    return ""


def _json_or_none(raw: bytes) -> object:
    try:
        return json.loads(raw or b"null")
    except json.JSONDecodeError:
        return None


def gitlab_api(domain: str, path: str, token: str = "") -> tuple[int, object]:
    """GET sur GitLab externe (TLS auto-signé accepté). Retourne (statut, corps
    json ou None si le corps n'est pas du JSON — pages HTML incluses)."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(f"https://gitlab.{domain}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, context=_insecure_ssl_ctx(), timeout=KUBECTL_TIMEOUT) as resp:
            return resp.status, _json_or_none(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _json_or_none(exc.read())
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, None


def gitlab_pat_status(domain: str, token: str) -> tuple[bool, str, int | None]:
    """Valide un PAT contre l'API : (valide, détail, jours restants avant expiration)."""
    status, body = gitlab_api(domain, "/api/v4/personal_access_tokens/self", token=token)
    if status in (401, 403):
        return False, f"PAT rejeté par l'API (HTTP {status})", None
    if status != 200 or not isinstance(body, dict):
        return False, f"API GitLab indisponible (HTTP {status or 'timeout'})", None
    if body.get("revoked") or not body.get("active", True):
        return False, "PAT révoqué ou inactif", None
    days_left = None
    if body.get("expires_at"):
        days_left = (date.fromisoformat(body["expires_at"]) - date.today()).days
        if days_left < 0:
            return False, f"PAT expiré depuis {-days_left}j", days_left
    detail = f"PAT '{body.get('name', '?')}' valide"
    if days_left is not None:
        detail += f" (expire dans {days_left}j)"
    return True, detail, days_left


# ---------------------------------------------------------------------------
# Checks de convergence — un par étape du bootstrap
# ---------------------------------------------------------------------------

def check_vm_images(values: dict[str, str]) -> tuple[bool, str]:
    out = run_out(["vagrant", "box", "list"], timeout=60)
    if out is None:
        return False, "vagrant box list indisponible"
    boxes = {line.split(" ", 1)[0] for line in out.splitlines() if line.strip()}
    missing = {"k8s-master", "k8s-worker"} - boxes
    if missing:
        return False, f"boxes absentes du registre Vagrant : {', '.join(sorted(missing))}"
    return True, "boxes k8s-master et k8s-worker enregistrées"


def check_cluster(values: dict[str, str]) -> tuple[bool, str]:
    out = kubectl_out(["get", "nodes", "--no-headers"])
    if out is None or not out.strip():
        return False, "cluster injoignable (kubectl get nodes)"
    nodes = [line.split() for line in out.strip().splitlines()]
    not_ready = [n[0] for n in nodes if len(n) > 1 and "Ready" not in n[1].split(",")]
    if not_ready:
        return False, f"nodes non Ready : {', '.join(not_ready)}"
    return True, f"{len(nodes)} node(s) Ready"


def check_argocd_ready(values: dict[str, str]) -> tuple[bool, str]:
    ns = values["ARGOCD_NAMESPACE"]
    ready = kubectl_out(["-n", ns, "get", "deploy", "argocd-server",
                         "-o", "jsonpath={.status.readyReplicas}"])
    if not (ready or "").strip() or int(ready.strip()) < 1:
        return False, "argocd-server sans replica Ready"
    apps = kubectl_out(["-n", ns, "get", "applications.argoproj.io", "--no-headers"])
    if apps is None or not apps.strip():
        return False, "aucune Application ArgoCD (root Application non appliquée ?)"
    return True, f"argocd-server Ready, {len(apps.strip().splitlines())} Application(s) déclarée(s)"


def check_apps_synced(values: dict[str, str]) -> tuple[bool, str]:
    ns = values["ARGOCD_NAMESPACE"]
    out = kubectl_out(["-n", ns, "get", "applications.argoproj.io", "-o",
                       "jsonpath={range .items[*]}{.metadata.name} {.status.sync.status} {.status.health.status}{\"\\n\"}{end}"])
    if out is None or not out.strip():
        return False, "aucune Application ArgoCD"
    bad = []
    for line in out.strip().splitlines():
        parts = line.split()
        name, sync, health = (parts + ["?", "?"])[:3]
        if sync != "Synced" or health != "Healthy":
            bad.append(f"{name} ({sync}/{health})")
    if bad:
        return False, f"Applications non Synced/Healthy : {', '.join(bad)}"
    return True, f"{len(out.strip().splitlines())} Application(s) Synced/Healthy"


def check_ghcr_secret(values: dict[str, str]) -> tuple[bool, str]:
    ns = values["ARGOCD_NAMESPACE"]
    out = kubectl_out(["-n", ns, "get", "secret", "ghcr-pull-secret", "-o", "name"])
    if out is None:
        return False, f"secret ghcr-pull-secret absent du namespace {ns}"
    return True, f"secret ghcr-pull-secret présent dans {ns}"


def check_gitlab_web(values: dict[str, str]) -> tuple[bool, str]:
    status, _ = gitlab_api(values["GITLAB_DOMAIN"], "/users/sign_in")
    if status != 200:
        return False, f"GitLab ne répond pas sur /users/sign_in (HTTP {status or 'timeout'})"
    return True, f"GitLab répond sur https://gitlab.{values['GITLAB_DOMAIN']}"


def check_git_creds(values: dict[str, str]) -> tuple[bool, str]:
    token = credential_fill(values["INTERNAL_GITLAB_HOST"])
    if not token:
        return False, f"aucune credential git pour {values['INTERNAL_GITLAB_HOST']}"
    ok, detail, _ = gitlab_pat_status(values["GITLAB_DOMAIN"], token)
    return ok, detail


# ---------------------------------------------------------------------------
# Checks applicatifs (inventaire platform-gitops)
# ---------------------------------------------------------------------------

def load_inventory_apps(values: dict[str, str]) -> list[dict]:
    apps_dir = repo_path(values, "GITOPS_REPO_ROOT") / "argocd" / "apps"
    apps = []
    for path in sorted(apps_dir.glob("*.yaml")):
        with path.open() as f:
            entry = yaml.safe_load(f) or {}
        if entry.get("name"):
            apps.append(entry)
    return apps


def check_app_projects(values: dict[str, str], app: dict, token: str) -> tuple[bool, str]:
    domain = values["GITLAB_DOMAIN"]
    group = app.get("group", "root")
    missing = []
    for repo in (app["name"], f"{app['name']}-iac"):
        project_id = urllib.parse.quote(f"{group}/{repo}", safe="")
        status, _ = gitlab_api(domain, f"/api/v4/projects/{project_id}", token=token)
        if status != 200:
            missing.append(f"{group}/{repo} (HTTP {status})")
    if missing:
        return False, f"projets GitLab absents : {', '.join(missing)}"
    return True, f"projets {group}/{app['name']} et {group}/{app['name']}-iac présents"


def check_app_pipeline(values: dict[str, str], app: dict, token: str) -> tuple[bool, str]:
    domain = values["GITLAB_DOMAIN"]
    group = app.get("group", "root")
    project_id = urllib.parse.quote(f"{group}/{app['name']}", safe="")
    status, body = gitlab_api(domain, f"/api/v4/projects/{project_id}/pipelines?per_page=1", token=token)
    if status != 200 or not isinstance(body, list):
        return False, f"pipelines de {group}/{app['name']} illisibles (HTTP {status})"
    if not body:
        return True, f"{group}/{app['name']} : aucun pipeline (pas encore de push)"
    latest = body[0]
    if latest.get("status") == "success":
        return True, f"{group}/{app['name']} : dernier pipeline success ({latest.get('ref')})"
    return False, f"{group}/{app['name']} : dernier pipeline {latest.get('status')} ({latest.get('web_url')})"
