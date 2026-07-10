#!/usr/bin/env python3
# Supprime le groupe gitlab.com k8s-gitops-lab (et tout ce qu'il contient :
# sous-groupes, projets, issues, MR, pipelines, state Terraform) pour
# permettre un bootstrap reproductible depuis zéro -- décision du
# 2026-07-10 (cf. cockpit/docs/backlog.md) : le state Terraform de
# gitlab-iac-com reste sur backend Kubernetes précisément pour ne pas
# dépendre d'un projet gitlab.com que ce script vient de supprimer.
#
# Note API : gitlab.com applique une rétention de 30 jours avant purge
# définitive des groupes top-level (l'option permanently_remove n'est
# utilisable que sur les sous-groupes déjà planifiés pour suppression --
# cf. doc API groups). Un simple DELETE suffit néanmoins pour un bootstrap
# immédiat : le groupe planifié pour suppression est aussitôt renommé, ce
# qui libère le chemin 'k8s-gitops-lab' pour une recréation immédiate ; le
# contenu de l'ancien groupe est purgé en arrière-plan après 30 jours.
#
# Usage :
#   GITLAB_TOKEN=<pat scope api> python3 scripts/gitlab-reset.py [--yes]
#   # ou via make :
#   GITLAB_TOKEN=<pat> make gitlab-reset
#
# Ne dépend d'aucun cluster/kubectl : le PAT est fourni directement par
# l'opérateur, pour pouvoir tourner avant même que le cluster existe.
import json
import os
import sys
import urllib.error
import urllib.request

GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
GROUP_PATH = os.environ.get("GITLAB_RESET_GROUP", "k8s-gitops-lab")


def api(path: str, token: str, method: str = "GET"):
    req = urllib.request.Request(
        f"{GITLAB_URL}/api/v4{path}",
        headers={"PRIVATE-TOKEN": token},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, (json.loads(body) if body else None)


def main() -> None:
    token = os.environ.get("GITLAB_TOKEN", "")
    if not token:
        sys.exit("GITLAB_TOKEN requis (PAT scope api).")

    status, group = api(f"/groups/{GROUP_PATH}", token)
    if status == 404:
        print(f"Groupe '{GROUP_PATH}' déjà absent, rien à faire.")
        return
    if status != 200:
        sys.exit(f"Erreur lecture groupe '{GROUP_PATH}': {status} {group}")

    if "--yes" not in sys.argv:
        reponse = input(
            f"Ceci va planifier la suppression du groupe '{GROUP_PATH}' "
            f"(id {group['id']}) et tout son contenu sur gitlab.com "
            f"(sous-groupes, projets, issues, MR, pipelines). Le chemin "
            f"'{GROUP_PATH}' sera libéré immédiatement pour recréation ; "
            f"le contenu sera purgé définitivement après 30 jours. "
            f"Continuer ? [y/N] "
        )
        if reponse.strip().lower() != "y":
            sys.exit("Annulé.")

    status, result = api(f"/groups/{group['id']}", token, method="DELETE")
    if status not in (200, 202, 204):
        sys.exit(f"Échec de suppression : {status} {result}")
    print(
        f"Groupe '{GROUP_PATH}' (id {group['id']}) planifié pour suppression "
        f"(purge définitive sous 30 jours ; le chemin est déjà libre)."
    )


if __name__ == "__main__":
    main()
