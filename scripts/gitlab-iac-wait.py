#!/usr/bin/env python3
"""Attend que le Terraform gitlab-iac-com (tf-controller) crée les projets GitLab.

Les projets GitLab applicatifs (groupes, repos <app>/<app>-iac, mirroring vers
GitHub) sont provisionnés par le CR Terraform Flux `gitlab-iac-com`
(platform-gitops/argocd/platform/tf-controller/terraform-gitlab-com.yaml),
appliqué de façon asynchrone après le sync ArgoCD. platform-verify interroge
l'API GitLab pour ces projets : sans cette attente, il s'exécute avant la fin
du `terraform apply` et échoue en 404 sur des ressources encore inexistantes.

Usage :
  CONFIG=platform.yml python3 scripts/gitlab-iac-wait.py
  # ou via make :
  make gitlab-projects-wait

Variables optionnelles :
  GITLAB_IAC_TIMEOUT  délai max en secondes (défaut 600)
"""
from __future__ import annotations

import os
import sys
import time

import platform_checks as pc

POLL_INTERVAL = 10  # secondes


def main() -> None:
    values = pc.load_values()

    timeout = int(os.environ.get("GITLAB_IAC_TIMEOUT", "600"))
    deadline = time.monotonic() + timeout
    while True:
        ok, detail = pc.check_gitlab_iac(values)
        if ok:
            print(f"OK : {detail}")
            return
        if time.monotonic() >= deadline:
            sys.exit(
                f"Timeout ({timeout}s) : {detail}.\n"
                "Vérifier l'état du CR Terraform et du tf-controller :\n"
                "  kubectl -n flux-system get terraforms.infra.contrib.fluxcd.io gitlab-iac-com\n"
                "  kubectl -n flux-system describe terraforms.infra.contrib.fluxcd.io gitlab-iac-com"
            )
        print(f"En attente ({detail})...")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
