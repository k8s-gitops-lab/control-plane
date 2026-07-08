#!/usr/bin/env bash
set -u

usage() {
  cat <<'USAGE'
Usage:
  scripts/clone-github-org.sh [options]

Options:
  -o, --org ORG          Organisation GitHub a cloner.
                         Par defaut: k8s-gitops-lab
  -d, --dest DIR         Dossier parent de destination.
                         Par defaut: parent du repo cockpit
  --ssh                  Clone via SSH.
  --https                Clone via HTTPS. Par defaut.
  --update               Fait git pull --ff-only dans les repos deja clones.
  --dry-run              Affiche les actions sans cloner ni mettre a jour.
  -h, --help             Affiche cette aide.

Variables:
  GITHUB_TOKEN           Token optionnel pour augmenter la limite d'API GitHub
                         ou acceder a des repos prives.

Exemples:
  scripts/clone-github-org.sh
  scripts/clone-github-org.sh --dest ..
  scripts/clone-github-org.sh --ssh --update
USAGE
}

org="k8s-gitops-lab"
dest=".."
protocol="https"
update_existing=false
dry_run=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    -o|--org)
      [ "$#" -ge 2 ] || { echo "Erreur: --org attend une valeur." >&2; exit 2; }
      org="$2"
      shift 2
      ;;
    -d|--dest)
      [ "$#" -ge 2 ] || { echo "Erreur: --dest attend une valeur." >&2; exit 2; }
      dest="$2"
      shift 2
      ;;
    --ssh)
      protocol="ssh"
      shift
      ;;
    --https)
      protocol="https"
      shift
      ;;
    --update)
      update_existing=true
      shift
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Erreur: argument inconnu: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Erreur: commande requise introuvable: $1" >&2
    exit 1
  fi
}

run() {
  if [ "$dry_run" = true ]; then
    printf 'DRY-RUN:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

need_cmd curl
need_cmd git
need_cmd python3

if [ "$dry_run" = false ]; then
  mkdir -p "$dest"
fi

repos_file="$(mktemp)"
trap 'rm -f "$repos_file"' EXIT

if ! ORG="$org" PROTOCOL="$protocol" python3 > "$repos_file" <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

org = os.environ["ORG"]
protocol = os.environ["PROTOCOL"]
token = os.environ.get("GITHUB_TOKEN")
page = 1

headers = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "poc-devops-clone-org",
}
if token:
    headers["Authorization"] = f"Bearer {token}"

while True:
    url = f"https://api.github.com/orgs/{org}/repos?per_page=100&page={page}&type=all"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request) as response:
            repos = json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Erreur GitHub API HTTP {exc.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Erreur GitHub API: {exc.reason}", file=sys.stderr)
        sys.exit(1)

    if not repos:
        break

    for repo in repos:
        clone_url = repo["ssh_url"] if protocol == "ssh" else repo["clone_url"]
        print(f"{repo['name']}\t{clone_url}")

    page += 1
PY
then
  exit 1
fi

if [ ! -s "$repos_file" ]; then
  echo "Aucun depot trouve pour l'organisation GitHub '$org'." >&2
  exit 1
fi

failure=0
repo_count=0

while IFS="$(printf '\t')" read -r name clone_url; do
  [ -n "$name" ] || continue
  repo_count=$((repo_count + 1))
  target="$dest/$name"

  printf '\n==> %s\n' "$name"

  if [ -d "$target/.git" ]; then
    echo "Depot deja clone: $target"
    if [ "$update_existing" = true ]; then
      echo "Mise a jour avec git pull --ff-only."
      if ! run git -C "$target" pull --ff-only; then
        echo "ERREUR: mise a jour echouee pour $name." >&2
        failure=1
      fi
    fi
    continue
  fi

  if [ -e "$target" ]; then
    echo "SKIP: $target existe mais n'est pas un depot Git." >&2
    failure=1
    continue
  fi

  echo "Clone depuis $clone_url"
  if ! run git clone "$clone_url" "$target"; then
    echo "ERREUR: clone echoue pour $name." >&2
    failure=1
  fi
done < "$repos_file"

echo
echo "$repo_count depot(s) traite(s)."
exit "$failure"
