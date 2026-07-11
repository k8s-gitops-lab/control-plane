#!/usr/bin/env python3
"""Réimporte dans le state Terraform en-cluster de gitlab-iac-com toute
ressource du module (gitlab_group, gitlab_project, gitlab_group_variable)
qui existe déjà sur gitlab.com mais n'est pas (ou plus) trackée.

Le groupe racine gitlab.com `k8s-gitops-lab` est persistant (création d'un
groupe top-level bloquée côté API par une vérification anti-abus, cf.
scripts/gitlab-reset.py) : il est créé une fois pour toutes manuellement via
l'UI, et `gitlab-reset.py` ne le supprime plus jamais. Les variables de
groupe (CUSTOM_CA_CERTS, INTERNAL_GITLAB_HOST, ...) vivent sur ce même
groupe racine et lui survivent donc tout autant. Les sous-groupes
(infra/shared-ci/hello-groupe) et projets sont en principe vidés par
`gitlab-reset.py` à chaque bootstrap -- mais si ce reset n'a pas tourné (ou
si un apply précédent les a recréés avant que son state ne soit persisté),
ils peuvent eux aussi exister déjà sans être trackés.

Le state Terraform de `gitlab-iac-com`, lui, vit dans un Secret Kubernetes
(`tfstate-default-gitlab-projects-iac-com`, namespace `flux-system`) qui est
neuf à chaque rebuild complet du cluster (`make platform-destroy` puis
`make platform-up`). Sans réimport, le premier `terraform apply` de
tf-controller tente de recréer une ressource déjà existante -> `403` (groupe
racine) ou `400 has already been taken` (sous-groupes, projets, variables),
ce qui bloque toute la chaîne (donc aussi les `git push gitlab` des 4 repos
GitLab-first).

Convergent : n'importe que ce qui manque encore au state en-cluster parmi
les ressources du module dont l'équivalent existe déjà sur gitlab.com. Si
tout est déjà à jour, ne fait rien.

Usage :
  GITLAB_TOKEN=<pat> GITHUB_TOKEN=<pat> python3 scripts/gitlab-tf-state-seed.py
  # ou via make (après que le cluster/flux-system existent, typiquement juste
  # après platform-bootstrap) :
  GITLAB_TOKEN=<pat> GITHUB_TOKEN=<pat> make gitlab-tf-state-seed

Nécessite le binaire `terraform` en local (même version que
gitlab-projects-iac/terraform/versions.tf) et un kubectl déjà pointé sur le
cluster cible.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse

import platform_checks as pc

BACKEND_SECRET_SUFFIX = "gitlab-projects-iac-com"
BACKEND_NAMESPACE = "flux-system"

# environment_scope = "*" pour toutes les gitlab_group_variable du module
# (main.tf) -- pas d'usage de scopes multiples ici, cf. format d'import
# `<group_id>:<key>:<environment_scope>` du provider.
ENVIRONMENT_SCOPE = "*"

GROUP_VARIABLE_BLOCK_RE = re.compile(
    r'resource\s+"gitlab_group_variable"\s+"(\w+)"\s*\{([^}]*)\}', re.DOTALL
)
GROUP_VARIABLE_KEY_RE = re.compile(r'key\s*=\s*"([A-Za-z0-9_]+)"')
GROUP_VARIABLE_GROUP_RE = re.compile(r'group\s*=\s*gitlab_group\.(\w+)\.id')

GROUP_BLOCK_RE = re.compile(r'resource\s+"gitlab_group"\s+"(\w+)"\s*\{([^}]*)\}', re.DOTALL)
PROJECT_BLOCK_RE = re.compile(r'resource\s+"gitlab_project"\s+"(\w+)"\s*\{([^}]*)\}', re.DOTALL)
PATH_RE = re.compile(r'\bpath\s*=\s*"([^"]+)"')
PARENT_ID_RE = re.compile(r'parent_id\s*=\s*gitlab_group\.(\w+)\.id')
NAMESPACE_ID_RE = re.compile(r'namespace_id\s*=\s*gitlab_group\.(\w+)\.id')


def parse_group_variable_resources(main_tf: str) -> list[tuple[str, str, str]]:
    """Extrait (nom_ressource, clé, nom_ressource_groupe_cible) de chaque bloc
    gitlab_group_variable de main.tf. Le groupe cible n'est pas toujours le
    groupe racine (ex. github_token_ci vit sur gitlab_group.infra) : lister
    uniquement les variables du groupe racine et importer avec son id serait
    faux pour ces variables-là (cf. R-02, cockpit/full-review-backlog.md)."""
    result = []
    for name, body in GROUP_VARIABLE_BLOCK_RE.findall(main_tf):
        key_match = GROUP_VARIABLE_KEY_RE.search(body)
        group_match = GROUP_VARIABLE_GROUP_RE.search(body)
        if key_match and group_match:
            result.append((name, key_match.group(1), group_match.group(1)))
    return result


def parse_groups(main_tf: str) -> dict[str, tuple[str, str | None]]:
    """Extrait {nom_ressource: (path, nom_ressource_parent_ou_None)} de main.tf.

    Ignore silencieusement les blocs for_each (ex. gitlab_group.app) : leur
    path/parent_id sont des expressions (each.key, ...), pas des littéraux --
    traités séparément par les instances dynamiques (cf. dynamic_app_groups).
    """
    groups = {}
    for name, body in GROUP_BLOCK_RE.findall(main_tf):
        path_match = PATH_RE.search(body)
        if path_match is None:
            continue
        parent_match = PARENT_ID_RE.search(body)
        groups[name] = (path_match.group(1), parent_match.group(1) if parent_match else None)
    return groups


def parse_projects(main_tf: str) -> dict[str, tuple[str, str]]:
    """Extrait {nom_ressource: (path, nom_ressource_groupe_parent)} de main.tf.

    Ignore silencieusement les blocs for_each (ex. gitlab_project.app) --
    cf. parse_groups.
    """
    projects = {}
    for name, body in PROJECT_BLOCK_RE.findall(main_tf):
        path_match = PATH_RE.search(body)
        namespace_match = NAMESPACE_ID_RE.search(body)
        if path_match is None or namespace_match is None:
            continue
        projects[name] = (path_match.group(1), namespace_match.group(1))
    return projects


def dynamic_app_groups(apps: list[dict]) -> set[str]:
    """Groupes dédiés par app (gitlab_group.app[for_each], cf. main.tf locals.app_groups)."""
    return {app["group"] for app in apps}


def dynamic_app_projects(apps: list[dict]) -> dict[str, str]:
    """{nom_projet: nom_groupe} pour <app> et <app>-iac (gitlab_project.app[for_each],
    cf. main.tf locals.app_projects)."""
    projects = {}
    for app in apps:
        projects[app["name"]] = app["group"]
        projects[f"{app['name']}-iac"] = app["group"]
    return projects


def full_group_path(groups: dict[str, tuple[str, str | None]], name: str) -> str:
    path, parent = groups[name]
    return path if parent is None else f"{full_group_path(groups, parent)}/{path}"


BACKEND_OVERRIDE_TF = """terraform {
  backend "kubernetes" {
    secret_suffix = "%s"
    namespace     = "%s"
    config_path   = "~/.kube/config"
  }
}
""" % (BACKEND_SECRET_SUFFIX, BACKEND_NAMESPACE)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, **kwargs)


def main() -> None:
    if not shutil.which("terraform"):
        sys.exit("binaire 'terraform' introuvable en local (requis pour l'import de state).")

    gitlab_token = os.environ.get("GITLAB_TOKEN", "")
    if not gitlab_token:
        sys.exit("GITLAB_TOKEN requis (PAT scope api).")
    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        sys.exit("GITHUB_TOKEN requis (scope repo -- toutes les variables du module doivent être fournies pour un import).")

    values = pc.load_values()

    terraform_dir = pc.repo_path(values, "GITLAB_IAC_REPO_ROOT") / "terraform"
    if not terraform_dir.is_dir():
        sys.exit(f"Module Terraform introuvable : {terraform_dir}")

    tracked, detail = pc.load_gitlab_tf_state_resources(values)
    tracked = tracked or set()

    group_path = values["GITLAB_GROUP"]
    status, group = pc.gitlab_api(
        values["GITLAB_URL"], f"/api/v4/groups/{urllib.parse.quote(group_path, safe='')}", token=gitlab_token
    )
    if status == 404:
        sys.exit(
            f"Groupe '{group_path}' introuvable sur {values['GITLAB_URL']} -- doit être créé une fois "
            "manuellement via l'UI (création top-level bloquée côté API), puis importé "
            "dans l'état Terraform (cf. commentaire sur gitlab_group.root dans "
            "gitlab-projects-iac/terraform/main.tf)."
        )
    if status != 200 or not isinstance(group, dict):
        sys.exit(f"Erreur lecture groupe '{group_path}': {status} {group}")
    group_id = group["id"]

    need_root_import = ("gitlab_group", "root") not in tracked

    main_tf = (terraform_dir / "main.tf").read_text()
    groups = parse_groups(main_tf)
    projects = parse_projects(main_tf)

    apps_file = terraform_dir / "apps.auto.tfvars.json"
    apps = json.loads(apps_file.read_text())["apps"] if apps_file.is_file() else []
    app_groups = dynamic_app_groups(apps)
    app_projects = dynamic_app_projects(apps)

    def lookup(kind: str, full_path: str) -> int | None:
        """Retourne l'id distant si la ressource existe déjà, None si 404."""
        status, body = pc.gitlab_api(
            values["GITLAB_URL"], f"/api/v4/{kind}/{urllib.parse.quote(full_path, safe='')}",
            token=gitlab_token,
        )
        if status == 404:
            return None
        if status != 200 or not isinstance(body, dict):
            sys.exit(f"Erreur lecture {kind} '{full_path}': {status} {body}")
        return body["id"]

    # Résout paresseusement l'id distant de chaque groupe nommé (mémoïsé) :
    # nécessaire à la fois pour l'import du groupe et pour celui de ses
    # variables (une gitlab_group_variable peut cibler un sous-groupe, ex.
    # infra pour github_token_ci -- cf. parse_group_variable_resources).
    group_remote_ids: dict[str, int] = {"root": group_id}

    def resolve_group_id(name: str) -> int | None:
        if name not in group_remote_ids:
            group_remote_ids[name] = lookup("groups", full_group_path(groups, name))
        return group_remote_ids[name]

    pending_groups: list[tuple[str, str, int]] = []
    for name in groups:
        if name == "root" or ("gitlab_group", name) in tracked:
            continue
        remote_id = resolve_group_id(name)
        if remote_id is not None:
            pending_groups.append((name, full_group_path(groups, name), remote_id))

    # Instances dynamiques de gitlab_group.app/gitlab_project.app (for_each
    # piloté par apps.auto.tfvars.json, cf. main.tf locals.app_groups/
    # app_projects) -- toujours enfants du groupe racine.
    root_path = full_group_path(groups, "root")
    for group in app_groups:
        indexed_name = f'app["{group}"]'
        if ("gitlab_group", indexed_name) in tracked:
            continue
        remote_id = lookup("groups", f"{root_path}/{group}")
        if remote_id is not None:
            pending_groups.append((indexed_name, f"{root_path}/{group}", remote_id))

    # Variables de groupe : chaque variable peut cibler un groupe différent
    # (root pour la plupart, infra pour GITHUB_TOKEN) -- lister les seules
    # variables du groupe racine ne suffit pas, et importer avec l'id racine
    # une variable d'un autre groupe créerait une ressource fantôme.
    group_variables_cache: dict[int, set[str]] = {}

    def remote_variable_keys(gid: int) -> set[str]:
        if gid not in group_variables_cache:
            status, remote_vars = pc.gitlab_api(
                values["GITLAB_URL"], f"/api/v4/groups/{gid}/variables?per_page=100", token=gitlab_token
            )
            if status != 200 or not isinstance(remote_vars, list):
                sys.exit(f"Erreur lecture variables du groupe {gid}: {status} {remote_vars}")
            group_variables_cache[gid] = {v["key"] for v in remote_vars}
        return group_variables_cache[gid]

    pending_variables: list[tuple[str, str, int]] = []
    for name, key, group_ref in parse_group_variable_resources(main_tf):
        if ("gitlab_group_variable", name) in tracked:
            continue
        var_group_id = resolve_group_id(group_ref)
        if var_group_id is not None and key in remote_variable_keys(var_group_id):
            pending_variables.append((name, key, var_group_id))

    # Projets : résout l'id distant de chaque projet nommé (littéral et
    # for_each), déjà tracké ou non -- nécessaire aussi pour seeder les
    # branch protections ci-dessous, qui dépendent de l'id projet et non du
    # suivi du gitlab_project lui-même.
    project_remote_ids: dict[str, int] = {}
    # adresse gitlab_project -> adresse gitlab_branch_protection correspondante
    branch_protection_targets: dict[str, str] = {
        "ci_templates": "ci_templates_main",
        "platform_gitops": "platform_gitops_main",
    }

    pending_projects: list[tuple[str, str, int]] = []
    for name, (path, parent) in projects.items():
        full_path = f"{full_group_path(groups, parent)}/{path}"
        remote_id = lookup("projects", full_path)
        if remote_id is None:
            continue
        project_remote_ids[name] = remote_id
        if ("gitlab_project", name) not in tracked:
            pending_projects.append((name, full_path, remote_id))

    for project_name, group in app_projects.items():
        indexed_name = f'app["{project_name}"]'
        full_path = f"{root_path}/{group}/{project_name}"
        remote_id = lookup("projects", full_path)
        if remote_id is None:
            continue
        project_remote_ids[indexed_name] = remote_id
        if ("gitlab_project", indexed_name) not in tracked:
            pending_projects.append((indexed_name, full_path, remote_id))
        branch_protection_targets[indexed_name] = f'app_main["{project_name}"]'

    # Branch protections : un projet survivant à un rebuild sans reset
    # préalable garde sa protection de branche "main" -- sans réimport, le
    # premier apply échoue en "Protected branch 'main' already exists".
    def protected_main_exists(project_id: int) -> bool:
        status, body = pc.gitlab_api(
            values["GITLAB_URL"], f"/api/v4/projects/{project_id}/protected_branches/main", token=gitlab_token
        )
        if status == 404:
            return False
        if status != 200:
            sys.exit(f"Erreur lecture protected_branches de project {project_id}: {status} {body}")
        return True

    pending_branch_protections: list[tuple[str, int, str]] = []
    for project_addr, bp_name in branch_protection_targets.items():
        if ("gitlab_branch_protection", bp_name) in tracked:
            continue
        project_id = project_remote_ids.get(project_addr)
        if project_id is not None and protected_main_exists(project_id):
            pending_branch_protections.append((bp_name, project_id, project_addr))

    if (not need_root_import and not pending_variables and not pending_groups
            and not pending_projects and not pending_branch_protections):
        print(f"OK : {detail or 'state en-cluster déjà à jour'}, rien à faire.")
        return
    if need_root_import:
        print(f"Seed nécessaire : {detail}.")
    if pending_groups:
        print("Sous-groupes déjà sur gitlab.com mais absents du state en-cluster : "
              + ", ".join(p for _, p, _ in pending_groups))
    if pending_projects:
        print("Projets déjà sur gitlab.com mais absents du state en-cluster : "
              + ", ".join(p for _, p, _ in pending_projects))
    if pending_variables:
        print("Variables déjà sur gitlab.com mais absentes du state en-cluster : "
              + ", ".join(key for _, key, _ in pending_variables))
    if pending_branch_protections:
        print("Protections de branche déjà sur gitlab.com mais absentes du state en-cluster : "
              + ", ".join(addr for addr, _, _ in pending_branch_protections))

    override_path = terraform_dir / "backend_override.tf"
    tf_env = {
        **os.environ,
        "TF_VAR_gitlab_token": gitlab_token,
        "TF_VAR_github_token": github_token,
        "TF_IN_AUTOMATION": "1",
    }

    override_path.write_text(BACKEND_OVERRIDE_TF)
    try:
        result = run(
            ["terraform", "init", "-input=false", "-reconfigure"],
            cwd=terraform_dir, env=tf_env, capture_output=True,
        )
        if result.returncode != 0:
            sys.exit(f"terraform init a échoué :\n{result.stdout}\n{result.stderr}")

        def do_import(address: str, real_id: str, label: str) -> None:
            result = run(
                ["terraform", "import", "-input=false", address, real_id],
                cwd=terraform_dir, env=tf_env, capture_output=True,
            )
            if result.returncode != 0:
                sys.exit(f"terraform import a échoué :\n{result.stdout}\n{result.stderr}")
            print(f"{address} ({label}) importé dans le state en-cluster.")

        if need_root_import:
            do_import("gitlab_group.root", str(group_id), f"id {group_id}")

        for name, full_path, remote_id in pending_groups:
            do_import(f"gitlab_group.{name}", str(remote_id), full_path)

        for name, full_path, remote_id in pending_projects:
            do_import(f"gitlab_project.{name}", str(remote_id), full_path)

        for name, key, var_group_id in pending_variables:
            import_id = f"{var_group_id}:{key}:{ENVIRONMENT_SCOPE}"
            do_import(f"gitlab_group_variable.{name}", import_id, key)

        for bp_name, project_id, project_addr in pending_branch_protections:
            do_import(f"gitlab_branch_protection.{bp_name}", f"{project_id}:main", project_addr)
    finally:
        override_path.unlink(missing_ok=True)
        shutil.rmtree(terraform_dir / ".terraform", ignore_errors=True)

    # Best effort : si le CR existe déjà (créé par ArgoCD avant ce seed) et a
    # échoué une première fois en 403, force un reconcile immédiat plutôt que
    # d'attendre son prochain intervalle (spec.interval: 1h).
    pc.kubectl_out([
        "-n", BACKEND_NAMESPACE, "annotate", "terraform.infra.contrib.fluxcd.io", "gitlab-iac-com",
        f"reconcile.fluxcd.io/requestedAt={int(time.time())}",
        "--overwrite",
    ])


if __name__ == "__main__":
    main()
