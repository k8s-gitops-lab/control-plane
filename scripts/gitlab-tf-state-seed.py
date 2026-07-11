#!/usr/bin/env python3
"""Importe gitlab_group.root dans le state Terraform en-cluster de gitlab-iac-com.

Le groupe racine gitlab.com `k8s-gitops-lab` est persistant (création d'un
groupe top-level bloquée côté API par une vérification anti-abus, cf.
scripts/gitlab-reset.py) : il est créé une fois pour toutes manuellement via
l'UI, et `gitlab-reset.py` ne le supprime plus jamais.

Le state Terraform de `gitlab-iac-com`, lui, vit dans un Secret Kubernetes
(`tfstate-default-gitlab-projects-iac-com`, namespace `flux-system`) qui est
neuf à chaque rebuild complet du cluster (`make platform-destroy` puis
`make platform-up`). Sans réimport, le premier `terraform apply` de
tf-controller tente de recréer `gitlab_group.root` -> `403 Forbidden`, ce qui
bloque toute la chaîne (sous-groupes/projets/variables gitlab.com jamais
créés, donc aussi les `git push gitlab` des 4 repos GitLab-first).

Convergent : si le state en-cluster connaît déjà `gitlab_group.root` (mêmes
critères que platform_checks.check_gitlab_tf_state_seeded), ne fait rien.

Usage :
  GITLAB_TOKEN=<pat> GITHUB_TOKEN=<pat> python3 scripts/gitlab-tf-state-seed.py
  # ou via make (après que le cluster/flux-system existent, typiquement juste
  # après platform-bootstrap) :
  GITLAB_TOKEN=<pat> GITHUB_TOKEN=<pat> make gitlab-tf-state-seed

Nécessite le binaire `terraform` en local (même version que
gitlab-projects-iac/terraform-gitlabcom/versions.tf) et un kubectl déjà
pointé sur le cluster cible.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.parse

import platform_checks as pc

BACKEND_SECRET_SUFFIX = "gitlab-projects-iac-com"
BACKEND_NAMESPACE = "flux-system"

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

    ok, detail = pc.check_gitlab_tf_state_seeded(values)
    if ok:
        print(f"OK : {detail}, rien à faire.")
        return
    print(f"Seed nécessaire : {detail}.")

    group_path = values["GITLAB_GROUP"]
    status, group = pc.gitlab_api(
        values["GITLAB_URL"], f"/api/v4/groups/{urllib.parse.quote(group_path, safe='')}", token=gitlab_token
    )
    if status == 404:
        sys.exit(
            f"Groupe '{group_path}' introuvable sur {values['GITLAB_URL']} -- doit être créé une fois "
            "manuellement via l'UI (création top-level bloquée côté API), puis importé "
            "dans l'état Terraform (cf. commentaire sur gitlab_group.root dans "
            "gitlab-projects-iac/terraform-gitlabcom/main.tf)."
        )
    if status != 200 or not isinstance(group, dict):
        sys.exit(f"Erreur lecture groupe '{group_path}': {status} {group}")
    group_id = group["id"]

    terraform_dir = pc.repo_path(values, "GITLAB_IAC_REPO_ROOT") / "terraform-gitlabcom"
    if not terraform_dir.is_dir():
        sys.exit(f"Module Terraform introuvable : {terraform_dir}")

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

        result = run(
            ["terraform", "import", "-input=false", "gitlab_group.root", str(group_id)],
            cwd=terraform_dir, env=tf_env, capture_output=True,
        )
        if result.returncode != 0:
            sys.exit(f"terraform import a échoué :\n{result.stdout}\n{result.stderr}")
        print(f"gitlab_group.root (id {group_id}) importé dans le state en-cluster.")
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
