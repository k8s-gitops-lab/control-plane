# Source control et depots runtime

Le POC distingue deux niveaux de depots, sur deux plateformes distinctes
depuis la bascule big bang du 2026-07-10 vers gitlab.com (GitLab self-hosted
in-cluster decommissionne, cf. `docs/backlog.md`).

## GitHub : amont de tous les depots, source lue par Flux/ArgoCD

Les repos du workspace sont geres sur GitHub. C'est l'amont de developpement :

- `cockpit`
- `infra-iac`
- `platform-bootstrap`
- `platform-gitops`
- `toolbox`
- `gitlab-projects-iac`
- `ci-templates`
- `helloworld`
- `helloworld-iac`

Les scripts de workspace peuvent cloner ou pousser cet amont, par exemple avec
`scripts/clone-github-org.sh` ou `scripts/commit-push-subprojects.sh --remote github`.

GitHub n'est pas qu'un amont de developpement : c'est aussi la source que
Flux lit en continu pour la plateforme elle-meme --

- `GitRepository flux-system/platform-gitops` (cote `platform-gitops`,
  `argocd/platform/tf-controller/platform-gitops-source.yaml`) pointe
  `https://github.com/k8s-gitops-lab/platform-gitops.git` : root Application
  ArgoCD, `flux-secrets/` (secrets SOPS), et les `ApplicationSet`
  (`argocd/managed/apps-appset.yaml`, `app-envs-appset.yaml`) qui generent
  les Applications par app/environnement lisent tous ce repo depuis GitHub.
- `GitRepository flux-system/gitlab-projects-iac` (meme dossier,
  `gitlab-repo.yaml`) pointe egalement GitHub -- le module Terraform qui
  provisionne les groupes/projets/variables gitlab.com est lui-meme lu
  depuis GitHub par le CR `gitlab-iac-com` (tf-controller).

Autrement dit : GitHub reste la source de verite pour tout ce qui concerne la
*plateforme* (bootstrap, GitOps racine, IaC gitlab.com), pas seulement pour le
developpement des repos.

## gitlab.com : execution CI et depots manifests lus par ArgoCD

Une fois la plateforme deployee, les projets applicatifs et leurs manifests
sont importes ou crees sur gitlab.com, groupe `k8s-gitops-lab`
(`https://gitlab.com/k8s-gitops-lab/...`, cf. `gitlab-projects-iac/terraform/main.tf`).
La CI s'y execute (runner autonome `gitlab-runner-com`), et les Applications
ArgoCD par environnement (`app-envs-appset.yaml`) lisent les depots manifests
`<app>-iac` directement depuis gitlab.com (`manifests.argocdRepoURL`, derive
par convention -- cf. `platform-bootstrap/scripts/platform_inventory.py` et
`cockpit/full-review-backlog.md` R-01).

**4 repos sont GitLab-first** : la CI s'exerce dessus, GitLab fait foi pour
eux, et GitHub n'en est qu'un miroir committe a la main --

- `ci-templates`
- `helloworld`
- `helloworld-iac`
- `platform-gitops` (le pipeline `onboard-apps` de `platform-gitops` y
  regenere et pousse les manifests generes)

Leur synchronisation (pull --rebase gitlab, push gitlab, puis miroir GitHub)
passe par `scripts/commit-gitlab-app-repos.sh` -- a l'inverse des autres
repos du workspace, pousses via `scripts/commit-push-subprojects.sh` avec
GitHub comme source de verite. Toujours pousser `gitlab` en premier pour ces
4 repos (cf. `CLAUDE.md`).

**Le miroir automatique GitLab -> GitHub a disparu avec la bascule.**
L'ancien mirror push (`gitlab_project_mirror.platform_gitops_to_github`,
instance locale) force-ecrasait `main` cote GitHub pour qu'il corresponde
exactement a GitLab -- decommissionne avec l'instance locale, et
volontairement pas reconstruit cote gitlab.com (`gitlab-projects-iac/terraform/main.tf`
ne declare plus aucune ressource de mirroring). La propagation GitLab -> GitHub
est donc **manuelle** pour ces 4 repos : dette assumee et suivie, cf.
`cockpit/full-review-backlog.md` R-03 (le script `commit-gitlab-app-repos.sh`
doit couvrir les 4 repos, pas seulement 3) et `docs/backlog.md`.

## PLATFORM_REPO_URL : mecanisme optionnel des scripts toolbox

Le flux courant et effectivement utilise pour faire evoluer l'inventaire
`platform-gitops` est la **merge request directe sur le projet GitLab**
`platform-gitops` (ajout de `argocd/apps/<app>.yaml`) : le pipeline
`.gitlab-ci.yml` (job `onboard-apps`) regenere les manifests et les pousse
cote GitLab au merge. Ce n'est pas un mecanisme toolbox.

`PLATFORM_REPO_URL` reste un mecanisme **optionnel**, utilise par certains
scripts `toolbox` (ex. `delete-project.py`) pour ouvrir une pull request
GitHub quand la variable est renseignee -- une alternative, pas le chemin
principal :

```sh
PLATFORM_REPO_URL=https://github.com/k8s-gitops-lab/platform-gitops.git \
  GITHUB_TOKEN=<token> \
  python3 toolbox/scripts/delete-project.py helloworld
```
