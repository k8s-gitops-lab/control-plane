set -u

usage() {
  cat <<'USAGE'
Usage:
  scripts/commit-push-subprojects.sh --message "message de commit" --remote github|gitlab|both

Options:
  -m, --message MESSAGE   Message utilise pour git commit.
  -r, --remote TARGET     Cible de push: github, gitlab ou both.
  -d, --dir DIR           Dossier parent contenant les repos.
                          Par defaut: parent du repo control-plane.
  -n, --dry-run           Affiche les actions sans modifier ni pousser.
  -h, --help              Affiche cette aide.

Hypotheses:
  - Le script parcourt les sous-repertoires directs contenant un dossier .git.
  - GitHub correspond au remote "origin".
  - GitLab correspond au remote "gitlab".
  - Le push se fait sur la branche courante: HEAD:<branche>.
USAGE
}

message=""
target=""
root_dir=".."
dry_run=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    -m|--message)
      [ "$#" -ge 2 ] || { echo "Erreur: --message attend une valeur." >&2; exit 2; }
      message="$2"
      shift 2
      ;;
    -r|--remote)
      [ "$#" -ge 2 ] || { echo "Erreur: --remote attend une valeur." >&2; exit 2; }
      target="$2"
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

case "$target" in
  github)
    remotes="origin"
    ;;
  gitlab)
    remotes="gitlab"
    ;;
  both)
    remotes="origin gitlab"
    ;;
  "")
    echo "Erreur: --remote est requis (github, gitlab ou both)." >&2
    usage >&2
    exit 2
    ;;
  *)
    echo "Erreur: cible --remote invalide: $target" >&2
    usage >&2
    exit 2
    ;;
esac

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
repo_count=0

for gitdir in "$root_dir"/*/.git; do
  [ -d "$gitdir" ] || continue
  repo="${gitdir%/.git}"
  repo_count=$((repo_count + 1))

  printf '\n==> %s\n' "$repo"

  branch="$(git -C "$repo" branch --show-current 2>/dev/null || true)"
  if [ -z "$branch" ]; then
    echo "SKIP: HEAD detache, impossible de pousser vers une branche courante." >&2
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

  for remote in $remotes; do
    if ! git -C "$repo" remote get-url "$remote" >/dev/null 2>&1; then
      echo "SKIP: remote '$remote' absent dans $repo."
      continue
    fi

    echo "Push vers $remote ($branch)."
    if ! run git -C "$repo" push "$remote" "HEAD:$branch"; then
      echo "ERREUR: git push vers '$remote' a echoue dans $repo." >&2
      failure=1
    fi
  done
done

if [ "$repo_count" -eq 0 ]; then
  echo "Aucun sous-repertoire Git trouve." >&2
  exit 1
fi

exit "$failure"
