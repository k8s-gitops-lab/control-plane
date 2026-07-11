#!/usr/bin/env bash
set -u

usage() {
  cat <<'USAGE'
Usage:
  scripts/commit-gitlab-app-repos.sh --message "message de commit"

Role:
  Synchronise les seuls repos committes cote GitLab runtime (templates CI et
  projets helloworld) : la CI s'exerce dessus, GitLab fait foi. D'ou la
  sequence pull --rebase depuis gitlab, push gitlab, puis miroir GitHub
  (force-with-lease). Pour les autres repos du workspace (GitHub fait foi),
  utiliser commit-push-subprojects.sh.

Options:
  -m, --message MESSAGE   Message utilise pour git commit.
  -d, --dir DIR           Dossier parent contenant les repos.
                          Par defaut: parent du repo cockpit.
  -n, --dry-run           Affiche les actions sans modifier ni pousser.
  -h, --help              Affiche cette aide.

Repos cibles:
  - helloworld
  - helloworld-iac
  - ci-templates
  - platform-gitops

Hypotheses:
  - Chaque repo cible est un sous-repertoire direct de DIR.
  - GitLab correspond au remote "gitlab".
  - GitHub correspond au remote "origin".
  - Le push se fait sur la branche courante: HEAD:<branche>.
USAGE
}

message=""
root_dir=".."
dry_run=false
repos="helloworld helloworld-iac ci-templates platform-gitops"

while [ "$#" -gt 0 ]; do
  case "$1" in
    -m|--message)
      [ "$#" -ge 2 ] || { echo "Erreur: --message attend une valeur." >&2; exit 2; }
      message="$2"
      shift 2
      ;;
    -d|--dir)
      [ "$#" -ge 2 ] || { echo "Erreur: --dir attend une valeur." >&2; exit 2; }
      root_dir="$2"
      shift 2
      ;;
    -n|--dry-run)
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

if [ -z "$message" ]; then
  echo "Erreur: le message de commit est requis." >&2
  usage >&2
  exit 2
fi

run() {
  if [ "$dry_run" = true ]; then
    printf 'DRY-RUN:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

has_changes() {
  [ -n "$(git -C "$1" status --porcelain)" ]
}

failure=0

for repo_name in $repos; do
  repo="$root_dir/$repo_name"

  printf '\n==> %s\n' "$repo"

  if [ ! -d "$repo/.git" ]; then
    echo "ERREUR: repo Git cible introuvable: $repo" >&2
    failure=1
    continue
  fi

  branch="$(git -C "$repo" branch --show-current 2>/dev/null || true)"
  if [ -z "$branch" ]; then
    echo "ERREUR: HEAD detache, impossible de pousser vers une branche courante." >&2
    failure=1
    continue
  fi

  if ! git -C "$repo" remote get-url gitlab >/dev/null 2>&1; then
    echo "ERREUR: remote 'gitlab' absent dans $repo." >&2
    failure=1
    continue
  fi

  if ! git -C "$repo" remote get-url origin >/dev/null 2>&1; then
    echo "ERREUR: remote 'origin' absent dans $repo." >&2
    failure=1
    continue
  fi

  if has_changes "$repo"; then
    echo "Commit des changements locaux."
    if ! run git -C "$repo" add -A; then
      echo "ERREUR: git add a echoue dans $repo." >&2
      failure=1
      continue
    fi
    if ! run git -C "$repo" commit -m "$message"; then
      echo "ERREUR: git commit a echoue dans $repo." >&2
      failure=1
      continue
    fi
  else
    echo "Aucun changement local a committer."
  fi

  echo "Pull rebase depuis gitlab ($branch)."
  if ! run git -C "$repo" pull --rebase gitlab "$branch"; then
    echo "ERREUR: git pull --rebase depuis 'gitlab' a echoue dans $repo." >&2
    failure=1
    continue
  fi

  echo "Push vers gitlab ($branch)."
  if ! run git -C "$repo" push gitlab "HEAD:$branch"; then
    echo "ERREUR: git push vers 'gitlab' a echoue dans $repo." >&2
    failure=1
  fi

  echo "Push vers origin/GitHub ($branch) [force-with-lease]."
  if ! run git -C "$repo" push --force-with-lease origin "HEAD:$branch"; then
    echo "ERREUR: git push --force-with-lease vers 'origin' a echoue dans $repo." >&2
    failure=1
  fi
done

exit "$failure"
