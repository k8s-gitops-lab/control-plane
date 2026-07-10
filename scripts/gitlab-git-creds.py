#!/usr/bin/env python3
# Valide le PAT gitlab.com fourni par l'operateur (GITLAB_TOKEN, meme
# convention que gitlab-reset.py) et le stocke dans git-credential pour
# GITLAB_URL. Convergent : si la credential stockee est deja valide (et loin
# de son expiration), ne fait rien ; sinon (re)stocke GITLAB_TOKEN.
# --rotate force le restockage meme si la credential en place est valide.
#
# Avant la bascule big bang vers gitlab.com (2026-07-10, cf.
# cockpit/docs/backlog.md), ce script provisionnait un PAT root a partir du
# secret K8s de l'instance GitLab locale -- decommissionnee depuis, il n'y a
# plus de secret a lire ni de PAT a creer automatiquement : le token est
# desormais gere par l'operateur cote gitlab.com (scope api).
#
# Usage :
#   GITLAB_TOKEN=<pat scope api> python3 scripts/gitlab-git-creds.py [--rotate]
#   # ou via make :
#   GITLAB_TOKEN=<pat> make gitlab-git-credentials
import argparse
import os
import subprocess
import sys
import urllib.parse

import platform_checks as pc

# En deçà de ce reliquat de validité, on prévient : le token gitlab.com
# n'est pas auto-renouvelable (l'opérateur le gère), mais on ne veut pas
# laisser une session bootstrap découvrir l'expiration en plein milieu.
RENEW_BEFORE_DAYS = 30


def existing_credential_ok(gitlab_url: str, host: str) -> bool:
    token = pc.credential_fill(host)
    if not token:
        return False
    ok, detail, days_left = pc.gitlab_pat_status(gitlab_url, token)
    if not ok:
        print(f"Credential existante invalide ({detail}), restockage depuis GITLAB_TOKEN.")
        return False
    if days_left is not None and days_left < RENEW_BEFORE_DAYS:
        print(f"Credential valide mais expire dans {days_left}j (< {RENEW_BEFORE_DAYS}j), restockage.")
        return False
    print(f"Credential existante pour {host} : {detail}. Rien a faire (--rotate pour forcer).")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rotate", action="store_true",
                        help="Force le restockage meme si la credential stockee est valide")
    args = parser.parse_args()

    gitlab_url = os.environ.get("GITLAB_URL") or pc.load_values()["GITLAB_URL"]
    host = urllib.parse.urlparse(gitlab_url).netloc

    if not args.rotate and existing_credential_ok(gitlab_url, host):
        return

    token = os.environ.get("GITLAB_TOKEN", "")
    if not token:
        sys.exit(
            "GITLAB_TOKEN requis (PAT gitlab.com scope api, gere par l'operateur -- "
            "aucune credential stockee valide a reutiliser)."
        )

    ok, detail, _ = pc.gitlab_pat_status(gitlab_url, token)
    if not ok:
        sys.exit(f"GITLAB_TOKEN invalide : {detail}")

    cred_input = (
        f"protocol=https\n"
        f"host={host}\n"
        f"username=oauth2\n"
        f"password={token}\n"
    )
    subprocess.run(["git", "credential", "approve"], input=cred_input.encode(), check=True)
    print(f"GITLAB_TOKEN stocke pour {host} ({detail}).")


if __name__ == "__main__":
    main()
