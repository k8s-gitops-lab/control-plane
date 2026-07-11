#!/usr/bin/env python3
# Vide le groupe gitlab.com k8s-gitops-lab (sous-groupes et projets directs)
# sans supprimer le groupe racine lui-même, pour permettre un bootstrap
# reproductible depuis zéro -- décision du 2026-07-11 (cf.
# cockpit/docs/backlog.md) : la création d'un groupe top-level est bloquée
# côté API gitlab.com par une vérification anti-abus (403 sans détail, y
# compris sur un chemin jamais utilisé -- vérifié le 2026-07-11), alors que
# le compte a bien can_create_group=true et un PAT scope api complet. Le
# groupe racine est donc créé une fois pour toutes manuellement via l'UI
# (qui affiche l'étape de vérification, contrairement à l'API) puis importé
# dans l'état Terraform (cf. terraform-gitlabcom/main.tf) ; ce script ne
# doit plus jamais le supprimer.
#
# Les sous-groupes/projets ne sont pas soumis à cette restriction : un
# simple DELETE suffit pour un bootstrap immédiat (le chemin est libéré
# tout de suite pour recréation ; le contenu est purgé en arrière-plan
# sous 30 jours, sans incidence ici).
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
        sys.exit(
            f"Groupe '{GROUP_PATH}' introuvable -- doit être créé une fois "
            f"manuellement via l'UI gitlab.com (création top-level bloquée "
            f"côté API, cf. commentaire en tête de ce script), puis importé "
            f"dans l'état Terraform (terraform-gitlabcom/main.tf)."
        )
    if status != 200:
        sys.exit(f"Erreur lecture groupe '{GROUP_PATH}': {status} {group}")

    status, subgroups = api(f"/groups/{group['id']}/subgroups", token)
    if status != 200:
        sys.exit(f"Erreur listage sous-groupes de '{GROUP_PATH}': {status} {subgroups}")

    status, projects = api(f"/groups/{group['id']}/projects?include_subgroups=false", token)
    if status != 200:
        sys.exit(f"Erreur listage projets de '{GROUP_PATH}': {status} {projects}")

    if not subgroups and not projects:
        print(f"Groupe '{GROUP_PATH}' déjà vide, rien à faire.")
        return

    if "--yes" not in sys.argv:
        noms = [g["full_path"] for g in subgroups] + [p["path_with_namespace"] for p in projects]
        reponse = input(
            f"Ceci va supprimer {len(subgroups)} sous-groupe(s) et "
            f"{len(projects)} projet(s) direct(s) sous '{GROUP_PATH}' : "
            f"{', '.join(noms)}. Le groupe racine '{GROUP_PATH}' (id "
            f"{group['id']}) est conservé. Continuer ? [y/N] "
        )
        if reponse.strip().lower() != "y":
            sys.exit("Annulé.")

    for sub in subgroups:
        status, result = api(f"/groups/{sub['id']}", token, method="DELETE")
        if status not in (200, 202, 204):
            sys.exit(f"Échec de suppression du sous-groupe '{sub['full_path']}': {status} {result}")
        print(f"Sous-groupe '{sub['full_path']}' (id {sub['id']}) supprimé.")

    for proj in projects:
        status, result = api(f"/projects/{proj['id']}", token, method="DELETE")
        if status not in (200, 202, 204):
            sys.exit(f"Échec de suppression du projet '{proj['path_with_namespace']}': {status} {result}")
        print(f"Projet '{proj['path_with_namespace']}' (id {proj['id']}) supprimé.")

    print(f"Groupe '{GROUP_PATH}' vidé (conservé) : sous-groupes et projets directs supprimés.")


if __name__ == "__main__":
    main()
