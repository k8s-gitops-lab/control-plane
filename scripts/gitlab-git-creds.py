#!/usr/bin/env python3
# Crée un PAT GitLab root et l'injecte dans git-credential pour l'URL interne
# cluster (http://INTERNAL_GITLAB_HOST). Idempotent : révoque et recrée le PAT
# si son nom existe déjà (utile après un 'git credential reject').
#
# Usage :
#   python3 scripts/gitlab-git-creds.py
#   # ou via make :
#   make gitlab-git-creds
import base64
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

GITLAB_NAMESPACE = os.environ.get("GITLAB_NAMESPACE", "gitlab")
GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.192.168.33.100.nip.io")
GITLAB_INSECURE_TLS = os.environ.get("GITLAB_INSECURE_TLS", "true").lower() not in ("0", "false", "no")
INTERNAL_GITLAB_HOST = os.environ.get(
    "INTERNAL_GITLAB_HOST",
    "gitlab-webservice-default.gitlab.svc.cluster.local:8181",
)
PAT_NAME = "git-local-dev"
PAT_SCOPES = ["read_repository", "write_repository", "api"]


def _ssl_ctx():
    ctx = ssl.create_default_context()
    if GITLAB_INSECURE_TLS:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def kube_secret_field(namespace, name, jsonpath):
    try:
        raw = subprocess.run(
            ["kubectl", "-n", namespace, "get", "secret", name, "-o", f"jsonpath={jsonpath}"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        print(f"Erreur kubectl : {exc.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return base64.b64decode(raw).decode() if raw else ""


def gitlab_post_form(path, data):
    req = urllib.request.Request(
        f"{GITLAB_URL}{path}",
        data=urllib.parse.urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=_ssl_ctx()) as resp:
        return json.loads(resp.read())


def gitlab_api(path, data=None, token=None, method=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"{GITLAB_URL}{path}",
        data=body,
        headers=headers,
        method=method or ("POST" if body else "GET"),
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_ctx()) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def main():
    root_password = kube_secret_field(
        GITLAB_NAMESPACE, "gitlab-gitlab-initial-root-password", "{.data.password}"
    )
    if not root_password:
        print("Mot de passe root GitLab introuvable dans le secret K8s.", file=sys.stderr)
        sys.exit(1)

    auth = gitlab_post_form("/oauth/token", {
        "grant_type": "password",
        "username": "root",
        "password": root_password,
    })
    bearer = auth.get("access_token", "")
    if not bearer or bearer == "null":
        print("Échec d'authentification à l'API GitLab.", file=sys.stderr)
        sys.exit(1)

    # Révoque le PAT existant pour permettre la rotation
    pats = gitlab_api("/api/v4/personal_access_tokens?user_id=1&state=active", token=bearer)
    for pat in pats if isinstance(pats, list) else []:
        if pat.get("name") == PAT_NAME:
            gitlab_api(f"/api/v4/personal_access_tokens/{pat['id']}", token=bearer, method="DELETE")
            print(f"PAT '{PAT_NAME}' (id={pat['id']}) révoqué pour rotation.")
            break

    expires_at = (date.today() + timedelta(days=365)).isoformat()
    result = gitlab_api(
        "/api/v4/users/1/personal_access_tokens",
        data={"name": PAT_NAME, "scopes": PAT_SCOPES, "expires_at": expires_at},
        token=bearer,
    )
    pat_token = result.get("token", "")
    if not pat_token:
        print(f"Échec de création du PAT : {result}", file=sys.stderr)
        sys.exit(1)

    cred_input = (
        f"protocol=http\n"
        f"host={INTERNAL_GITLAB_HOST}\n"
        f"username=root\n"
        f"password={pat_token}\n"
    )
    subprocess.run(["git", "credential", "approve"], input=cred_input.encode(), check=True)
    print(f"PAT '{PAT_NAME}' créé et stocké pour {INTERNAL_GITLAB_HOST} (expire {expires_at}).")


if __name__ == "__main__":
    main()
