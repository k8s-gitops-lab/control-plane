# Règles de travail — poc-devops

## Gouvernance du développement

Toute contribution respecte les trois axes de maîtrise — produit, code,
architecture — décrits dans `AGENTS.md`, section « Gouvernance du
développement » (qui fait foi).

## Workflow Git

Ne jamais modifier les fichiers directement dans l'interface GitLab (éditeur
web, merge request, etc.). Toujours : modifier en local, committer, pousser.

Tous les repos ont `origin` → `https://github.com/k8s-gitops-lab/<repo>`.
Seuls 4 repos ont aussi un remote `gitlab` (**gitlab.com**, groupe
`k8s-gitops-lab` — migration depuis l'instance self-hosted du cluster,
décommissionnée le 2026-07-10, cf. `docs/backlog.md`, bascule big bang) :

- `ci-templates` → `gitlab.com/k8s-gitops-lab/shared-ci/ci-templates`
- `helloworld` → `gitlab.com/k8s-gitops-lab/hello-groupe/helloworld`
- `helloworld-iac` → `gitlab.com/k8s-gitops-lab/hello-groupe/helloworld-iac`
- `platform-gitops` → `gitlab.com/k8s-gitops-lab/infra/platform-gitops`

Où pousser (détail et rôles : `docs/source-control.md`) :

- Repos GitHub-first (défaut) :
  ```bash
  git push origin main
  ```
- Repos GitLab-first (`ci-templates`, `helloworld`, `helloworld-iac`,
  `platform-gitops` — la CI s'exerce sur GitLab, qui fait foi pour eux) :
  committer côté GitLab puis répercuter sur GitHub
  (`scripts/commit-gitlab-app-repos.sh` enchaîne pull --rebase, push GitLab
  et miroir GitHub) :
  ```bash
  git push gitlab main
  git push origin main
  ```
  Pour les tags : `git push gitlab --tags && git push origin --tags`.

  `platform-gitops` avait en plus un miroir GitLab→GitHub automatique côté
  instance locale (force-écrasait `origin/main`) — décommissionné avec
  l'instance locale ; pas encore reconstruit côté gitlab.com (dette,
  cf. `docs/backlog.md`). En attendant, pousser `gitlab` puis `origin`
  reste la marche à suivre pour ces 4 repos.

## Règle : tout commit finit sur GitHub

Tout commit doit être poussé sur `origin` (GitHub) — c'est non négociable, y
compris quand `gitlab` est injoignable depuis l'environnement courant (dans
ce cas, pousser sur GitHub quand même et repousser sur GitLab plus tard).

Si un commit est créé côté GitLab (ex. merge d'une MR), il doit aussi être
répercuté sur GitHub : récupérer la branche depuis `gitlab` et la pousser
vers `origin` avant de considérer le travail terminé.

## Documentation

Pas d'OpenWiki dans ce dépôt. Entrées réelles :

- `README.md` : parcours utilisateurs, usage, séquence `platform-up`.
- `docs/repo-map.md` : rôle de chaque dépôt du workspace.
- `docs/backlog.md` : backlog produit et historique des décisions (dont la
  migration GitLab self-hosted → gitlab.com).
