#!/usr/bin/env python3
"""Smoke test de bout en bout de la plateforme.

Vérifie les critères d'acceptation observables du PRD : cluster Ready,
GitLab et ArgoCD répondent, toutes les Applications ArgoCD sont
Synced/Healthy, le secret GHCR est en place, le PAT git-credential est
valide, et pour chaque app de l'inventaire les projets GitLab existent et
le dernier pipeline est vert.

Usage :
  python3 scripts/platform-verify.py [--quiet]
  # ou via make :
  make platform-verify

Code retour : 0 si tout passe, 1 sinon. --quiet n'affiche que les échecs
et le résumé (utilisé comme check de convergence par bootstrap.py).
"""
from __future__ import annotations

import argparse
import sys

import platform_checks as pc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true",
                        help="N'affiche que les échecs et le résumé")
    args = parser.parse_args()

    values = pc.load_values()
    results: list[tuple[str, bool, str]] = []

    def run(label: str, ok: bool, detail: str) -> None:
        results.append((label, ok, detail))
        if not ok:
            print(f"  ✗ {label} — {detail}")
        elif not args.quiet:
            print(f"  ✓ {label} — {detail}")

    # Plateforme
    run("cluster", *pc.check_cluster(values))
    run("gitlab-web", *pc.check_gitlab_web(values))
    run("argocd", *pc.check_argocd_ready(values))
    run("argocd-apps", *pc.check_apps_synced(values))
    run("ghcr-pull-secret", *pc.check_ghcr_secret(values))

    token = pc.credential_fill(values["INTERNAL_GITLAB_HOST"])
    pat_ok, pat_detail, _ = pc.gitlab_pat_status(values["GITLAB_DOMAIN"], token) if token \
        else (False, f"aucune credential git pour {values['INTERNAL_GITLAB_HOST']} (make gitlab-git-creds)", None)
    run("gitlab-pat", pat_ok, pat_detail)

    # Apps de l'inventaire (nécessite le PAT pour interroger l'API)
    apps = pc.load_inventory_apps(values)
    if not apps and not args.quiet:
        print("  - inventaire : aucune app déclarée, checks applicatifs sautés")
    for app in apps:
        if not pat_ok:
            run(f"app/{app['name']}", False, "check sauté : PAT GitLab indisponible")
            continue
        run(f"app/{app['name']}/projets", *pc.check_app_projects(values, app, token))
        run(f"app/{app['name']}/pipeline", *pc.check_app_pipeline(values, app, token))

    failed = [label for label, ok, _ in results if not ok]
    total = len(results)
    if failed:
        print(f"\nplatform-verify : {total - len(failed)}/{total} checks OK — échecs : {', '.join(failed)}")
        sys.exit(1)
    print(f"platform-verify : {total}/{total} checks OK")


if __name__ == "__main__":
    main()
