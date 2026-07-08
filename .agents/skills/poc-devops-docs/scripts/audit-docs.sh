#!/usr/bin/env bash
# Audit de la documentation du workspace poc-devops.
# Usage : audit-docs.sh [racine-du-workspace]
# Defaut : la racine deduite de l'emplacement du skill (../../../../..).
# Le script SIGNALE ; il ne modifie rien. Certains ecarts sont des choix
# assumes (cf. SKILL.md, section "Structure documentaire par repo").
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="${1:-$(cd "$SCRIPT_DIR/../../../../.." && pwd)}"
REPOS=(control-plane infrastructure platform-cicd platform-gitops
       gitlab-projects-iac ci-templates toolbox helloworld helloworld-iac)

warn=0
note() { echo "  [!] $*"; warn=$((warn + 1)); }

echo "Workspace : $WS"

# --- 1. Layout attendu par repo -------------------------------------------
echo
echo "== Layout documentaire =="
for r in "${REPOS[@]}"; do
  d="$WS/$r"
  [ -d "$d" ] || { note "$r : repo absent du workspace"; continue; }
  echo "-- $r"
  for f in README.md AGENTS.md docs/prd.md docs/spec-fonctionnelle.md docs/spec-technique.md; do
    [ -f "$d/$f" ] || note "$r/$f manquant"
  done
done

# --- 2. Liens relatifs morts dans les .md ---------------------------------
echo
echo "== Liens relatifs morts (.md) =="
for r in "${REPOS[@]}"; do
  d="$WS/$r"
  [ -d "$d" ] || continue
  while IFS= read -r md; do
    rel="${md#"$WS"/}"
    # liens markdown [txt](cible) — on ne garde que les cibles relatives
    { grep -oE '\]\(([^)#]+)' "$md" 2>/dev/null || true; } | sed 's/^](//' \
    | { grep -vE '^(https?:|mailto:|/|<)' || true; } | sort -u \
    | while IFS= read -r target; do
        [ -n "$target" ] || continue
        if [ ! -e "$(dirname "$md")/$target" ]; then
          echo "  [!] $rel -> $target (introuvable)"
        fi
      done
  done < <(find "$d" -maxdepth 2 -name '*.md' -not -path '*/.git/*' -not -path '*/.agents/*')
done | sort -u | tee /tmp/audit-docs-links.$$ 
extra=$(wc -l < /tmp/audit-docs-links.$$); rm -f /tmp/audit-docs-links.$$
warn=$((warn + extra))

# --- 3. Cibles make citees vs cibles reelles ------------------------------
echo
echo "== Cibles make citees dans la doc =="
for r in "${REPOS[@]}"; do
  d="$WS/$r"
  [ -f "$d/Makefile" ] || continue
  real_targets="$(grep -oE '^[a-zA-Z0-9_%-]+:' "$d/Makefile" | tr -d ':' | sort -u)"
  # regex alternative des cibles reelles, % (pattern make) devient .*
  targets_re="^($(echo "$real_targets" | sed 's/%/.*/' | paste -sd'|' -))$"
  while IFS= read -r md; do
    rel="${md#"$WS"/}"
    { grep -ohE 'make [a-z][a-z0-9-]+' "$md" 2>/dev/null || true; } | awk '{print $2}' | sort -u \
    | while IFS= read -r t; do
        # les cibles pattern (ex. bootstrap-from-%) matchent via .*
        if ! echo "$t" | grep -qE "$targets_re"; then
          echo "  [!] $rel cite 'make $t' absent de $r/Makefile"
        fi
      done
  done < <(find "$d" -maxdepth 2 -name '*.md' -not -path '*/.git/*' -not -path '*/.agents/*')
done | sort -u | tee /tmp/audit-docs-make.$$ 
extra=$(wc -l < /tmp/audit-docs-make.$$); rm -f /tmp/audit-docs-make.$$
warn=$((warn + extra))

echo
if [ "$warn" -eq 0 ]; then
  echo "OK : aucun ecart detecte."
else
  echo "$warn signalement(s). Chaque signalement se tranche a la main (certains ecarts sont assumes)."
fi
