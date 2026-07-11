# cockpit

Point d'entree operateur optionnel du POC.

Ce repo ne remplace pas les repos existants et ne doit pas devenir une
dependance d'execution pour eux. Chaque projet reste autonome : ses Makefiles,
valeurs par defaut et procedures doivent continuer a fonctionner depuis son
propre repo.

`cockpit` fournit seulement un profil local pour enchaîner les commandes
des repos specialises avec des variables explicites :

- `infra-iac` : socle Kubernetes, storage, Gateway API, MetalLB, Traefik.
- `platform-bootstrap` : bootstrap ArgoCD, credentials GitLab et runner.
- `platform-gitops` : configuration suivie en continu par ArgoCD (dont GitLab).
- `toolbox` : utilitaires operateur hors bootstrap principal.

La vue globale du projet vit ici :

- `docs/repo-map.md` : role de chaque repo du workspace.
- `docs/source-control.md` : separation GitHub amont vs GitLab runtime.
- `docs/prd.md` : intention, périmètre et limites du POC.
- `docs/spec-fonctionnelle.md` : flow Git, CI/CD et parcours applicatif.
- `docs/spec-technique.md` : détails d'implémentation et contraintes infra.
- `docs/prod-constraints.md` : contraintes à prévoir pour une cible prod.
- `docs/security-poc.md` : posture sécurité du POC (clé age, SOPS, secret GHCR).
- `docs/backlog.md` : backlog produit (initiative extensibilité/généricité
  et entretien courant).

## Parcours utilisateurs

Deux profils utilisent ce workspace, à deux moments différents.

### Parcours 1 — Un·e opérateur DevOps met en place la plateforme

Prérequis : le workspace cloné (`bash scripts/clone-github-org.sh` clone les
repos de l'organisation GitHub côte à côte), et le secret GHCR paramétré une
première fois :

```sh
make ghcr-token-init
```

Cette commande crée la clé age locale si besoin, demande un compte GitHub et
un PAT (scope `read:packages`, saisie masquée), puis chiffre
`platform-gitops/flux-secrets/ghcr-pull-secret.yaml`. Voir
`docs/security-poc.md` pour le détail. Committer/pousser les fichiers
modifiés de `platform-gitops` (`.sops.yaml`,
`flux-secrets/ghcr-pull-secret.yaml`) — Flux lit le repo GitHub — avant de
lancer :

```sh
make platform-up
```

Cette unique commande construit tout depuis zéro : images VM Packer, cluster
Kubernetes, puis bootstrap plateforme (ArgoCD, GitLab, secret GHCR, runner),
et se termine par un smoke test de bout en bout. Elle est idempotente : en
cas d'échec elle reprend automatiquement à l'étape utile, et à chaque
relance elle re-vérifie que les étapes déjà faites sont toujours vraies
(boxes présentes, cluster joignable, secret en place, PAT valide) avant de
les sauter — c'est une commande de réconciliation, pas seulement de reprise
(voir "Usage" ci-dessous pour le détail des étapes).

Une fois la commande terminée :

- `make platform-verify` : rejoue le smoke test à tout moment (cluster,
  GitLab, Applications ArgoCD Synced/Healthy, secret GHCR, PAT, projets et
  pipelines des apps de l'inventaire).
- `make argocd-status` : état de synchronisation ArgoCD.
- `make argocd-password` : récupérer le mot de passe admin initial.
- La plateforme est prête à accueillir des projets applicatifs (Parcours 2).

Pour le détail de chaque étape :

- `infra-iac/AGENTS.md` : socle Kubernetes (Packer, Vagrant, Ansible).
- `platform-bootstrap/AGENTS.md` : bootstrap ArgoCD, GitLab et credentials.
- `platform-gitops/AGENTS.md` : ce qu'ArgoCD synchronise en continu ensuite.

### Parcours 2 — Une équipe applicative crée un projet

Prérequis : la plateforme est déjà en place (Parcours 1 déjà réalisé par
l'opérateur) et `make gitlab-git-credentials` a été exécuté au moins une fois
(PAT gitlab.com stocké dans git-credential, `GITLAB_TOKEN` requis la première
fois).

1. Écrire le code de l'app (`<app>/`) et son dépôt de manifests
   (`<app>-iac/`), en réutilisant `ci-templates` pour la CI (voir
   `helloworld`/`helloworld-iac` comme exemple de référence).
2. Ouvrir une merge request directement sur le projet GitLab
   `platform-gitops` ajoutant `argocd/apps/<app>.yaml` (schéma
   `argocd/apps.schema.json`, seuls `name` et `group` sont requis) :
   `apiVersion: platform/v1` (recommandé), `name`, `group`, `description`,
   `services`, `hasPreprod`. Tout le reste (`repoURL`, `argocdRepoURL`
   gitlab.com, namespaces, URLs, destinations ArgoCD) est dérivé par
   convention par `platform-bootstrap/scripts/platform_inventory.py` (le
   fichier de même nom dans `toolbox` en est une copie). Un `environments:`
   explicite reste possible pour surcharger entièrement la séquence
   dev/rec/preprod/prod (voir `helloworld.yaml` comme exemple).
3. Au merge de cette MR, la chaîne se déclenche automatiquement : régénération
   des manifests ArgoCD (`ApplicationSet`/`AppProject`), régénération de
   l'inventaire Terraform (`apps.auto.tfvars.json`), création des projets
   GitLab correspondants (vides), puis synchronisation ArgoCD des
   environnements déclarés. Aucune action manuelle requise à cette étape.
4. Pousser le code initial vers les projets GitLab nouvellement créés — ils
   sont créés vides, sauf pour une app historique déclarée
   `importFromGithub: true` :
   ```sh
   git -C <app> remote add gitlab https://gitlab.com/k8s-gitops-lab/<group>/<app>.git
   git -C <app> push gitlab main
   git -C <app>-iac remote add gitlab https://gitlab.com/k8s-gitops-lab/<group>/<app>-iac.git
   git -C <app>-iac push gitlab main
   ```
   (`<group>` est celui déclaré à l'étape 2.)
5. Vérifier le résultat : le projet apparaît dans GitLab
   (`https://gitlab.com/k8s-gitops-lab/<group>/`), les `Application`
   ArgoCD correspondantes sont visibles et synchronisées (`make argocd-status` ou
   l'UI ArgoCD), et le premier merge sur `<app>` déclenche le pipeline
   `ci-templates` (build once, déploiement automatique vers `dev`).
6. Les push suivants sur `<app>` suivent le pipeline `ci-templates` (build
   once, promotion dev → rec → preprod → prod par tag).

Pour le détail de chaque étape : `toolbox/README.md` (scripts d'onboarding)
et `ci-templates/README.md` (contrat CI applicatif).

## Usage

Parcours complet avec images VM Packer :

```sh
make platform-up
```

Variables d'environnement requises pour la séquence complète (vérifiées en
préflight avant tout lancement de Packer/Vagrant — `make platform-up` échoue
immédiatement avec la liste des manques) :

- `GITLAB_TOKEN` : PAT gitlab.com scope `api`, requis par `gitlab-tf-state-seed`
  et par `gitlab-git-credentials` en l'absence de credential déjà stockée et
  valide.
- `GITHUB_TOKEN` : PAT GitHub scope `repo`, requis par `gitlab-tf-state-seed`
  (toutes les variables du module Terraform doivent être fournies pour
  l'import).
- Binaires locaux : `vagrant`, `packer` (étape `vm-images`), `kubectl`
  (à partir de `platform-bootstrap`), `terraform` (`gitlab-tf-state-seed`,
  même version que `gitlab-projects-iac/terraform/versions.tf`).

Cette commande enchaine, avec reprise automatique en cas d'échec
(`.bootstrap-state.json`, durées par étape incluses — `make
platform-bootstrap-status` pour les consulter) :

- `make vm-images` : construit puis enregistre les boxes Vagrant `k8s-master`
  et `k8s-worker`.
- `make cluster-from-images` : demarre les VMs et initialise le cluster depuis
  ces boxes.
- `make snapshot-cluster` : prend un snapshot VirtualBox de `master-01`/
  `worker-01` juste apres la fin du provisioning du cluster (nom
  `SNAPSHOT_NAME`, defaut `cluster-ready`) — permet de rejouer uniquement le
  bootstrap CI/CD ensuite sans repasser par Packer/Vagrant/kubeadm (voir
  `make platform-from-snapshot` plus bas).
- `make platform-bootstrap` : installe ArgoCD puis bootstrappe GitLab, le
  runner et les apps plateforme (les images applicatives sont poussées sur
  GHCR, pas sur un registry interne).
- `make gitlab-tf-state-seed` : réimporte dans le state Terraform en-cluster
  les ressources gitlab.com déjà existantes (groupe racine, variables,
  sous-groupes/projets/branch protections survivants) — évite les échecs
  `403`/`already been taken` du premier apply après un rebuild complet du
  cluster sans reset préalable. Nécessite `GITLAB_TOKEN` et `GITHUB_TOKEN`.
- `make ghcr-pull-secret-wait` : attend que Flux depose le secret GHCR source
  (dechiffre depuis `platform-gitops/flux-secrets/`) dans le namespace
  `argocd` ; External Secrets Operator le distribue ensuite en continu sous
  le nom `ghcr-pull` dans chaque namespace applicatif labellise par
  `render-argocd-apps.py`.
- `make gitlab-git-credentials` : verifie le PAT gitlab.com stocke dans
  `git-credential`, et ne le (re)stocke depuis `GITLAB_TOKEN` que s'il est
  absent, invalide ou a moins de 30 jours d'expiration (`--rotate` pour
  forcer). Le token lui-meme est gere par l'operateur cote gitlab.com (meme
  PAT que `GITLAB_TOKEN` utilise par `gitlab-reset`/`platform-destroy`).
- `make gitlab-projects-wait` : attend que le Terraform `gitlab-iac`
  (tf-controller) ait cree les projets GitLab applicatifs.
- `make argocd-apps-wait` : attend que toutes les Applications ArgoCD soient
  Synced/Healthy (apres la creation des projets GitLab, ArgoCD doit encore
  rafraichir les repos et deployer — timeout `ARGOCD_APPS_TIMEOUT`,
  defaut 900 s).
- `make platform-verify` : smoke test final de bout en bout.

Avant de sauter une étape marquée terminée, `bootstrap.py` rejoue son check
de convergence (`scripts/platform_checks.py`) ; une étape dont l'état ne
tient plus (VM détruite, secret supprimé, PAT révoqué…) redevient le point
de reprise. `--no-verify` désactive cette re-vérification. Un récapitulatif
des durées par étape est affiché en fin de séquence.

Les etapes restent executables separement :

```sh
make env
make vm-images
make cluster-from-images
make snapshot-cluster
make platform-bootstrap
make gitlab-tf-state-seed
make ghcr-pull-secret-wait
make gitlab-git-credentials
make gitlab-projects-wait
make argocd-apps-wait
make platform-verify
```

Pour rejouer uniquement la séquence complète avec reprise automatique :
`make platform-up` (depuis zéro) ou `make platform-provision` (sans
reconstruire les images Packer existantes).

### Rejouer uniquement le CI/CD depuis un snapshot

Une fois `make snapshot-cluster` passé au moins une fois, `make
platform-from-snapshot` restaure les VMs `master-01`/`worker-01` à cet état
(cluster prêt, CI/CD pas encore déployé) puis reprend directement à
`platform-bootstrap` — sans repasser par Packer/Vagrant/kubeadm :

```sh
make platform-from-snapshot
# equivalent a :
#   make restore-cluster
#   python3 scripts/bootstrap.py --from platform-bootstrap
```

`SNAPSHOT_NAME` (defaut `cluster-ready`) est commun à `snapshot-cluster`,
`restore-cluster` et `platform-from-snapshot`.

En cas d'échec pendant le bootstrap plateforme, reprendre à l'étape utile sans
rejouer tout le début :

```sh
make platform-bootstrap START_AT=gitlab-tf-credentials
```

`platform.yml` est un profil operateur local, pas la source de verite des
projets. Toute valeur necessaire a l'autonomie d'un repo doit rester declaree
dans ce repo, puis peut etre surchargee ici pour orchestrer le POC complet.

Les compromis de securite propres au POC sont documentes dans
`docs/security-poc.md`, incluant la gestion des secrets chiffres SOPS
(`platform-gitops/flux-secrets/ghcr-pull-secret.yaml`).

## Scripts workspace

Les scripts operateur du workspace sont versionnes dans `scripts/` :

```sh
# Initialise/met a jour le workspace depuis l'org GitHub
bash scripts/clone-github-org.sh

# Repos du workspace : GitHub fait foi
bash scripts/commit-push-subprojects.sh --message "..." --remote github

# Repos committes cote GitLab runtime (ci-templates, helloworld*) :
# GitLab fait foi, miroir GitHub en aval
bash scripts/commit-gitlab-app-repos.sh --message "..."
```

Les repos du POC sont des depots GitHub independants, clones cote a cote dans
le meme dossier parent (pas de sous-modules Git) ; `clone-github-org.sh`
initialise ou met a jour le workspace complet.
