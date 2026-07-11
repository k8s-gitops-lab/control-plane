"""Chargement de platform.yml et checks de convergence partagés.

Utilisé par export-env.py (config seule), bootstrap.py (checks par étape),
platform-verify.py (smoke test de bout en bout) et gitlab-git-creds.py
(validation du PAT existant). Chaque check retourne (ok, détail) sans rien
imprimer : l'appelant décide du format d'affichage.
"""
from __future__ import annotations

import base64
import gzip
import json
import os
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
DEFAULT_SNAPSHOT_NAME = "cluster-ready"


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
        "GITLAB_URL": platform["gitlab"]["url"],
        "GITLAB_GROUP": platform["gitlab"]["group"],
        "ARGOCD_NAMESPACE": platform["argocd"]["namespace"],
        "ARGOCD_VERSION": versions["argocd"],
        "INFRASTRUCTURE_REPO": repos["infrastructure"],
        "PLATFORM_REPO_ROOT": repos["platform"],
        "GITOPS_REPO_ROOT": repos["gitops"],
        "TOOLBOX_REPO": repos["toolbox"],
        "GITLAB_IAC_REPO_ROOT": repos["gitlabIac"],
    }


def repo_path(values: dict[str, str], key: str) -> Path:
    path = Path(values[key])
    return path if path.is_absolute() else ROOT / path


# ---------------------------------------------------------------------------
# Primitives (kubectl, git credential, API GitLab)
# ---------------------------------------------------------------------------

def run_out(cmd: list[str], timeout: int = KUBECTL_TIMEOUT, **kwargs) -> str | None:
    """Retourne stdout si la commande réussit, None sinon (échec ou timeout)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    return result.stdout if result.returncode == 0 else None


def kubectl_out(args: list[str]) -> str | None:
    return run_out(["kubectl", f"--request-timeout={KUBECTL_TIMEOUT - 5}s", *args])


def credential_fill(host: str) -> str:
    """Retourne le mot de passe stocké dans git-credential pour cet hôte, '' si absent."""
    out = run_out(
        ["git", "credential", "fill"],
        input=f"protocol=https\nhost={host}\n\n",
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


def gitlab_api(base_url: str, path: str, token: str = "") -> tuple[int, object]:
    """GET sur l'API GitLab. Retourne (statut, corps json ou None si le corps
    n'est pas du JSON — pages HTML incluses)."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(f"{base_url.rstrip('/')}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=KUBECTL_TIMEOUT) as resp:
            return resp.status, _json_or_none(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _json_or_none(exc.read())
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, None


def gitlab_pat_status(base_url: str, token: str) -> tuple[bool, str, int | None]:
    """Valide un PAT contre l'API : (valide, détail, jours restants avant expiration)."""
    status, body = gitlab_api(base_url, "/api/v4/personal_access_tokens/self", token=token)
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


def check_vm_snapshot(values: dict[str, str]) -> tuple[bool, str]:
    name = os.environ.get("SNAPSHOT_NAME", DEFAULT_SNAPSHOT_NAME)
    vagrant_dir = repo_path(values, "INFRASTRUCTURE_REPO") / "vagrant"
    missing = []
    for vm in ("master-01", "worker-01"):
        out = run_out(["vagrant", "snapshot", "list", vm], timeout=30, cwd=vagrant_dir)
        if out is None or name not in out.splitlines():
            missing.append(vm)
    if missing:
        return False, f"snapshot '{name}' absent sur : {', '.join(missing)}"
    return True, f"snapshot '{name}' présent sur master-01 et worker-01"


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


def check_git_creds(values: dict[str, str]) -> tuple[bool, str]:
    host = urllib.parse.urlparse(values["GITLAB_URL"]).netloc
    token = credential_fill(host)
    if not token:
        return False, f"aucune credential git pour {host}"
    ok, detail, _ = gitlab_pat_status(values["GITLAB_URL"], token)
    return ok, detail


GITLAB_IAC_TERRAFORM_CR = "gitlab-iac-com"
GITLAB_IAC_TFSTATE_SECRET = "tfstate-default-gitlab-projects-iac-com"


def check_gitlab_iac(values: dict[str, str]) -> tuple[bool, str]:
    """Vérifie que le CR Terraform Flux gitlab-iac-com a fini son apply.

    Les projets GitLab applicatifs (groupes, <app>/<app>-iac, mirroring) sont
    créés de façon asynchrone par ce CR après le sync ArgoCD. Tant qu'il n'est
    pas Ready, l'API GitLab renvoie 404 sur ces projets.
    """
    out = kubectl_out([
        "-n", "flux-system", "get", "terraforms.infra.contrib.fluxcd.io", GITLAB_IAC_TERRAFORM_CR,
        "-o", 'jsonpath={.status.conditions[?(@.type=="Ready")].status}'
               '|{.status.conditions[?(@.type=="Ready")].message}',
    ])
    if out is None:
        return False, f"CR Terraform {GITLAB_IAC_TERRAFORM_CR} introuvable (namespace flux-system) — tf-controller pas encore convergé ?"
    status, _, message = out.partition("|")
    status, message = status.strip(), message.strip()
    if status != "True":
        return False, f"Terraform {GITLAB_IAC_TERRAFORM_CR} non appliqué (Ready={status or '?'} : {message or 'apply en cours'})"
    return True, f"Terraform {GITLAB_IAC_TERRAFORM_CR} appliqué ({message})"


def check_gitlab_tf_state_seeded(values: dict[str, str]) -> tuple[bool, str]:
    """Vérifie que le state Terraform en-cluster de gitlab-iac-com connaît déjà
    gitlab_group.root.

    Le groupe racine gitlab.com est persistant (création de groupe top-level
    bloquée côté API, cf. scripts/gitlab-reset.py) mais le Secret Kubernetes
    qui porte le state Terraform est neuf à chaque rebuild complet du cluster
    -- sans réimport, le premier apply de tf-controller tente de recréer ce
    groupe et échoue en 403. Voir scripts/gitlab-tf-state-seed.py.
    """
    raw = kubectl_out([
        "-n", "flux-system", "get", "secret", GITLAB_IAC_TFSTATE_SECRET,
        "-o", "jsonpath={.data.tfstate}",
    ])
    if not (raw or "").strip():
        return False, f"secret {GITLAB_IAC_TFSTATE_SECRET} absent (namespace flux-system)"
    try:
        state = json.loads(gzip.decompress(base64.b64decode(raw)))
    except (ValueError, OSError):
        return False, f"secret {GITLAB_IAC_TFSTATE_SECRET} illisible (state corrompu ?)"
    seeded = any(
        r.get("type") == "gitlab_group" and r.get("name") == "root"
        for r in state.get("resources", [])
    )
    if not seeded:
        return False, "gitlab_group.root absent du state Terraform en-cluster"
    return True, "gitlab_group.root présent dans le state Terraform en-cluster"


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
    base_url = values["GITLAB_URL"]
    group = f"{values['GITLAB_GROUP']}/{app.get('group', 'root')}"
    missing = []
    for repo in (app["name"], f"{app['name']}-iac"):
        project_id = urllib.parse.quote(f"{group}/{repo}", safe="")
        status, _ = gitlab_api(base_url, f"/api/v4/projects/{project_id}", token=token)
        if status != 200:
            missing.append(f"{group}/{repo} (HTTP {status})")
    if missing:
        return False, f"projets GitLab absents : {', '.join(missing)}"
    return True, f"projets {group}/{app['name']} et {group}/{app['name']}-iac présents"


def _gitlab_file_content(base_url: str, project_id: str, file_path: str, ref: str, token: str) -> bytes | None:
    encoded = urllib.parse.quote(file_path, safe="")
    status, body = gitlab_api(
        base_url,
        f"/api/v4/projects/{project_id}/repository/files/{encoded}?ref={urllib.parse.quote(ref, safe='')}",
        token=token)
    if status != 200 or not isinstance(body, dict):
        return None
    try:
        return base64.b64decode(body["content"])
    except (KeyError, ValueError):
        return None


class _CIYamlLoader(yaml.SafeLoader):
    """SafeLoader tolérant aux tags GitLab CI (!reference), chargés comme None."""


_CIYamlLoader.add_constructor(None, lambda loader, node: None)


def _yaml_component_includes(raw: bytes) -> set[str]:
    """Références `include: component:` d'un YAML CI (multi-document accepté)."""
    try:
        docs = list(yaml.load_all(raw, Loader=_CIYamlLoader))
    except yaml.YAMLError:
        return set()
    refs = set()
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        includes = doc.get("include") or []
        if isinstance(includes, dict):
            includes = [includes]
        if not isinstance(includes, list):
            continue
        refs |= {inc["component"] for inc in includes
                 if isinstance(inc, dict) and isinstance(inc.get("component"), str)}
    return refs


def check_app_ci_components(values: dict[str, str], app: dict, token: str) -> tuple[bool, str]:
    """Vérifie que les composants CI inclus par l'app existent au ref pointé.

    Reproduit la résolution GitLab d'un `include: component:` : le fichier
    templates/<nom>/template.yml (ou templates/<nom>.yml) doit exister dans
    le projet du composant au tag/branche référencé, sinon le pipeline échoue
    en « component content not found ». La vérification est récursive (les
    composants inclus par les composants sont suivis) et signale les hôtes
    étrangers (GitLab ne résout que les composants de sa propre instance).
    Lit le .gitlab-ci.yml de la branche par défaut du projet GitLab de l'app
    (celui qui fait foi pour la CI).
    """
    base_url = values["GITLAB_URL"]
    group = f"{values['GITLAB_GROUP']}/{app.get('group', 'root')}"
    project = f"{group}/{app['name']}"
    project_id = urllib.parse.quote(project, safe="")

    status, body = gitlab_api(base_url, f"/api/v4/projects/{project_id}", token=token)
    if status != 200 or not isinstance(body, dict):
        return False, f"projet {project} illisible (HTTP {status})"
    default_branch = body.get("default_branch") or "main"

    status, body = gitlab_api(
        base_url,
        f"/api/v4/projects/{project_id}/repository/files/.gitlab-ci.yml?ref={default_branch}",
        token=token)
    if status == 404:
        return True, f"{project} : pas de .gitlab-ci.yml sur {default_branch}"
    if status != 200 or not isinstance(body, dict):
        return False, f".gitlab-ci.yml de {project} illisible (HTTP {status})"
    try:
        raw = base64.b64decode(body["content"])
    except (KeyError, ValueError):
        return False, f".gitlab-ci.yml de {project} invalide"

    queue = sorted(_yaml_component_includes(raw))
    if not queue:
        return True, f"{project} : aucun composant CI inclus"

    known_hosts = ("$CI_SERVER_FQDN", urllib.parse.urlparse(base_url).netloc)
    seen: set[str] = set()
    bad = []
    resolved = 0
    while queue:
        component = queue.pop(0)
        if component in seen:
            continue
        seen.add(component)
        location, _, ref = component.partition("@")
        segments = location.split("/")
        if not ref or len(segments) < 3:
            bad.append(f"{component} (référence malformée)")
            continue
        # <fqdn>/<chemin/du/projet>/<nom-du-composant>@<ref>
        if segments[0] not in known_hosts:
            bad.append(f"{component} (hôte {segments[0]} : GitLab ne résout que "
                       "les composants de sa propre instance)")
            continue
        comp_project, comp_name = "/".join(segments[1:-1]), segments[-1]
        comp_id = urllib.parse.quote(comp_project, safe="")
        if ref == "~latest":
            status, releases = gitlab_api(
                base_url, f"/api/v4/projects/{comp_id}/releases?per_page=1", token=token)
            if status != 200 or not releases:
                bad.append(f"{comp_project}/{comp_name}@~latest (aucune release)")
            continue
        content = None
        for path in (f"templates/{comp_name}/template.yml", f"templates/{comp_name}.yml"):
            content = _gitlab_file_content(base_url, comp_id, path, ref, token)
            if content is not None:
                break
        if content is None:
            tag_status, _ = gitlab_api(
                base_url,
                f"/api/v4/projects/{comp_id}/repository/tags/{urllib.parse.quote(ref, safe='')}",
                token=token)
            if tag_status == 200:
                bad.append(f"{comp_project}/{comp_name}@{ref} (tag présent mais template absent)")
            else:
                _, tags = gitlab_api(
                    base_url, f"/api/v4/projects/{comp_id}/repository/tags?per_page=1", token=token)
                latest = tags[0].get("name", "?") if isinstance(tags, list) and tags else "aucun"
                bad.append(f"{comp_project}/{comp_name}@{ref} (ref inexistant, dernier tag : {latest})")
            continue
        resolved += 1
        queue.extend(sorted(_yaml_component_includes(content) - seen))
    if bad:
        return False, f"composants CI introuvables : {', '.join(bad)}"
    return True, f"{resolved} composant(s) CI résolus (imbriqués compris) sur {default_branch}"


def check_app_pipeline(values: dict[str, str], app: dict, token: str) -> tuple[bool, str]:
    base_url = values["GITLAB_URL"]
    group = f"{values['GITLAB_GROUP']}/{app.get('group', 'root')}"
    project_id = urllib.parse.quote(f"{group}/{app['name']}", safe="")
    status, body = gitlab_api(base_url, f"/api/v4/projects/{project_id}/pipelines?per_page=1", token=token)
    if status != 200 or not isinstance(body, list):
        return False, f"pipelines de {group}/{app['name']} illisibles (HTTP {status})"
    if not body:
        return True, f"{group}/{app['name']} : aucun pipeline (pas encore de push)"
    latest = body[0]
    if latest.get("status") == "success":
        return True, f"{group}/{app['name']} : dernier pipeline success ({latest.get('ref')})"
    return False, f"{group}/{app['name']} : dernier pipeline {latest.get('status')} ({latest.get('web_url')})"
