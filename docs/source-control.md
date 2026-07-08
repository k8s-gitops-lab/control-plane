# Source control et depots runtime

Le POC distingue deux niveaux de depots.

## GitHub : source amont

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

## GitLab : depots runtime de la plateforme deployee

Une fois la plateforme deployee, les projets sont importes ou seedes dans le
GitLab interne. La CI, les depots applicatifs et les lectures ArgoCD en
cluster utilisent ces depots GitLab.

Seuls les templates CI et les projets applicatifs d'exemple (`ci-templates`,
`helloworld`, `helloworld-iac`) se committent directement cote GitLab : la CI
s'exerce dessus, GitLab fait foi pour eux, et GitHub n'en est qu'un miroir.
Leur synchronisation (pull --rebase GitLab, push GitLab, miroir GitHub) passe
par `scripts/commit-gitlab-app-repos.sh` — a l'inverse des autres repos du
workspace, pousses via `scripts/commit-push-subprojects.sh` avec GitHub comme
source de verite.

## PLATFORM_REPO_URL : depot source GitOps

`PLATFORM_REPO_URL` des commandes toolbox pointe vers le depot source
`platform-gitops` sur GitHub. C'est ce depot qui recoit les branches et pull
requests d'evolution de l'inventaire GitOps.

L'ajout d'une app se fait par pull request directe sur `platform-gitops`
(ajout de `argocd/apps/<app>.yaml`), pas via un script toolbox.

```sh
PLATFORM_REPO_URL=https://github.com/k8s-gitops-lab/platform-gitops.git \
  GITHUB_TOKEN=<token> \
  python3 toolbox/scripts/delete-project.py helloworld
```

Les depots applicatifs lus par ArgoCD utilisent l'URL interne GitLab
`gitlab-webservice-default.gitlab.svc.cluster.local:8181` quand il synchronise
les manifests applicatifs.

## Exception de bootstrap

Le tout premier bootstrap d'ArgoCD peut encore referencer GitHub pour lire la
configuration GitOps initiale, car le GitLab interne n'existe pas encore ou
n'est pas encore alimente. Cette exception sert a amorcer la plateforme et a
eviter une dependance circulaire : GitLab est lui-meme decrit dans la
configuration GitOps.

Apres import/seed dans GitLab, les operations runtime de la plateforme utilisent
les projets GitLab de la plateforme deployee. Les evolutions du code source et
de l'inventaire GitOps restent proposees sur GitHub via `PLATFORM_REPO_URL`.

Concretement :

- `PLATFORM_REPO_URL` doit pointer vers
  `https://github.com/k8s-gitops-lab/platform-gitops.git`.
- Les depots applicatifs lus par ArgoCD utilisent l'URL interne GitLab
  `http://gitlab-webservice-default.gitlab.svc.cluster.local:8181/...`.
- Les references GitLab internes dans l'ApplicationSet applicatif concernent
  les depots manifests des applications, pas le depot source `platform-gitops`.
