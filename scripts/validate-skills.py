#!/usr/bin/env python3
"""Valide les skills de .agents/skills/ : frontmatter + chemins cites.

- Frontmatter : name (1-64 chars, [a-z0-9-], pas de tirets en bord/doubles)
  et description (non vide, <= 1024 chars) obligatoires.
- Anti-derive : tout chemin `repo/chemin/fichier` cite dans un SKILL.md et
  pointant vers un repo voisin du workspace doit exister sur le disque.
  C'est ce controle qui attrape les references a des playbooks/roles/docs
  renommes dans les repos voisins.

Sortie non nulle si au moins une erreur. Usage : validate-skills.py [racine].
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
WORKSPACE = ROOT.parent
REPOS = {
    "cockpit", "infra-iac", "platform-bootstrap", "platform-gitops",
    "gitlab-projects-iac", "ci-templates", "toolbox", "helloworld", "helloworld-iac",
}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# chemin `repo/xxx` cite en inline-code, ex. `platform-bootstrap/ansible/playbook-platform.yml`
PATH_RE = re.compile(r"`([a-z0-9-]+)/([A-Za-z0-9_./*-]+)`")

errors: list[str] = []


def frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip("'\"")
    return fields


def check_skill(skill_md: Path) -> None:
    rel = skill_md.relative_to(ROOT)
    text = skill_md.read_text(encoding="utf-8")

    fm = frontmatter(text)
    name = fm.get("name", "")
    desc = fm.get("description", "")
    if not name or not NAME_RE.match(name) or len(name) > 64:
        errors.append(f"{rel}: frontmatter 'name' invalide ou absent ({name!r})")
    if not desc:
        errors.append(f"{rel}: frontmatter 'description' absent (le skill ne sera pas charge)")
    elif len(desc) > 1024:
        errors.append(f"{rel}: description > 1024 caracteres")

    for repo, path in PATH_RE.findall(text):
        if repo not in REPOS:
            continue
        target = WORKSPACE / repo / path
        if "*" in path:  # glob (ex. packer/*.pkr.hcl)
            if not list((WORKSPACE / repo).glob(path)):
                errors.append(f"{rel}: glob cite sans correspondance : {repo}/{path}")
        elif not target.exists():
            errors.append(f"{rel}: chemin cite introuvable : {repo}/{path}")

    # scripts references par le skill (scripts/xxx.sh) doivent exister et etre executables
    for script in re.findall(r"`?(scripts/[A-Za-z0-9_.-]+\.(?:sh|py))`?", text):
        p = skill_md.parent / script
        if not p.exists():
            errors.append(f"{rel}: script du skill introuvable : {script}")


def main() -> int:
    skills_dir = ROOT / ".agents" / "skills"
    skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    if not skill_files:
        print(f"Aucun skill trouve sous {skills_dir}", file=sys.stderr)
        return 1
    for skill_md in skill_files:
        check_skill(skill_md)
    if errors:
        for e in errors:
            print(f"ERREUR: {e}", file=sys.stderr)
        return 1
    print(f"OK: {len(skill_files)} skill(s) valide(s) (frontmatter + chemins cites)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
