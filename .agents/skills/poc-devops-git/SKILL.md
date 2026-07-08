---
name: poc-devops-git
description: 'Dual-remote Git workflow for the poc-devops workspace: every repo pushes to both GitHub (origin, source of truth) and the local GitLab (gitlab remote). Use when committing, pushing, tagging, merging GitLab MRs, or recovering when one remote is unreachable in any poc-devops repo.'
---

# Workflow Git poc-devops

Regles extraites de `control-plane/CLAUDE.md` (@ f040e3e, 2026-07-07).
Valables pour **tous** les repos du workspace.

## Les deux remotes

| Remote | URL | Role |
|---|---|---|
| `origin` | `https://github.com/k8s-gitops-lab/<repo>` | **Fait foi** — non negociable |
| `gitlab` | `http(s)://gitlab.192.168.33.100.nip.io/root/<repo>` | GitLab local du POC (CI/CD) |

## Procedure standard (commit -> double push)

Jamais de modification dans l'interface GitLab (editeur web, MR, etc.).
Toujours :

```bash
# 1. Modifier en local, puis committer
git add <fichiers> && git commit -m "<message>"

# 2. Pousser vers LES DEUX remotes, GitHub d'abord
git push origin main
git push gitlab main

# Tags : idem
git push origin --tags
git push gitlab --tags
```

Un push vers un seul remote n'est **pas** un travail termine.

## Cas particuliers

- **GitLab injoignable** : pousser sur GitHub quand meme (il fait foi),
  repousser sur `gitlab` des qu'il est de nouveau accessible. L'inverse
  (GitLab seul, GitHub plus tard) n'est pas acceptable.
- **Commit cree cote GitLab** (ex. merge d'une MR d'inventaire) : recuperer
  la branche depuis `gitlab` et la pousser vers `origin` avant de considerer
  le travail termine :

  ```bash
  git fetch gitlab
  git merge --ff-only gitlab/main   # ou la branche concernee
  git push origin main
  ```

- **Verifier la synchro des deux remotes** :

  ```bash
  git fetch origin gitlab
  git rev-parse origin/main gitlab/main   # doivent etre identiques
  ```

## A faire / A eviter

### A faire

- Terminer chaque sequence de travail par le double push (origin puis
  gitlab), y compris pour les tags.
- Apres un merge de MR cote GitLab, repercuter immediatement sur GitHub.
- En fin de tache multi-repo, verifier la synchro de chaque repo touche.

### A eviter

- Editer un fichier via l'interface web GitLab.
- Pousser sur `gitlab` sans pousser sur `origin` (GitHub fait foi).
- Considerer un travail termine avec un seul remote a jour.
