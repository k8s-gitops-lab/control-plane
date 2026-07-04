# control-plane

Point d'entree operateur optionnel du POC.

Ce repo ne remplace pas les repos existants et ne doit pas devenir une
dependance d'execution pour eux. Chaque projet reste autonome : ses Makefiles,
valeurs par defaut et procedures doivent continuer a fonctionner depuis son
propre repo.

`control-plane` fournit seulement un profil local pour enchaîner les commandes
des repos specialises avec des variables explicites :

- `infrastructure` : socle Kubernetes, storage, Gateway API, MetalLB, Traefik.
- `platform-cicd` : bootstrap ArgoCD, credentials GitLab et runner.
- `platform-gitops` : configuration suivie en continu par ArgoCD (dont GitLab).
- `toolbox` : utilitaires operateur hors bootstrap principal.

La vue globale du projet vit ici :

- `docs/repo-map.md` : role de chaque repo du workspace.
- `docs/source-control.md` : separation GitHub amont vs GitLab runtime.
- `docs/prd.md` : intention, périmètre et limites du POC.
- `docs/spec-fonctionnelle.md` : flow Git, CI/CD et parcours applicatif.
- `docs/spec-technique.md` : détails d'implémentation et contraintes infra.
- `docs/prod-constraints.md` : contraintes à prévoir pour une cible prod.

## Parcours utilisateurs

Deux profils utilisent ce workspace, à deux moments différents.

### Parcours 1 — Un·e opérateur DevOps met en place la plateforme

Prérequis : le workspace cloné avec ses sous-modules (`git submodule update
--init --recursive`).

```sh
make platform-up
```

Cette unique commande construit tout depuis zéro : images VM Packer, cluster
Kubernetes, puis bootstrap plateforme (ArgoCD, GitLab, secret GHCR, runner).
Elle est idempotente et reprend automatiquement à l'étape utile en cas
d'échec (voir "Usage" ci-dessous pour le détail des 5 étapes et les reprises
manuelles).

Une fois la commande terminée :

- `make status` : état de synchronisation ArgoCD.
- `make argocd-password` / `make gitlab-password` : récupérer les mots de
  passe admin initiaux.
- La plateforme est prête à accueillir des projets applicatifs (Parcours 2).

Pour le détail de chaque étape :

- `infrastructure/AGENTS.md` : socle Kubernetes (Packer, Vagrant, Ansible).
- `platform-cicd/AGENTS.md` : bootstrap ArgoCD, GitLab et credentials.
- `platform-gitops/AGENTS.md` : ce qu'ArgoCD synchronise en continu ensuite.

### Parcours 2 — Une équipe applicative crée un projet

Prérequis : la plateforme est déjà en place (Parcours 1 déjà réalisé par
l'opérateur) et `make gitlab-git-creds` a été exécuté au moins une fois
(credentials git stockées pour l'hôte GitLab interne).

1. Écrire le code de l'app (`<app>/`) et son dépôt de manifests
   (`<app>-iac/`), en réutilisant `ci-templates` pour la CI (voir
   `helloworld`/`helloworld-iac` comme exemple de référence).
2. Ouvrir une merge request directement sur le projet GitLab
   `platform-gitops` ajoutant `argocd/apps/<app>.yaml` au format minimal :
   `name`, `group`, `description`, `services`, `hasPreprod`. Tout le reste
   (`repoURL`, namespaces, URLs, destinations ArgoCD) est dérivé par
   convention par `toolbox/scripts/platform_inventory.py`.
3. Au merge de cette MR, la chaîne se déclenche automatiquement : régénération
   des manifests ArgoCD (`ApplicationSet`/`AppProject`), régénération de
   l'inventaire Terraform (`apps.auto.tfvars.json`), création des projets
   GitLab correspondants (vides), puis synchronisation ArgoCD des
   environnements déclarés. Aucune action manuelle requise à cette étape.
4. Pousser le code initial vers les projets GitLab nouvellement créés — ils
   sont créés vides, sauf pour une app historique déclarée
   `importFromGithub: true` :
   ```sh
   git -C <app> remote add gitlab https://gitlab.192.168.33.100.nip.io/<group>/<app>.git
   git -C <app> push gitlab main
   git -C <app>-iac remote add gitlab https://gitlab.192.168.33.100.nip.io/<group>/<app>-iac.git
   git -C <app>-iac push gitlab main
   ```
   (`<group>` est celui déclaré à l'étape 2.)
5. Vérifier le résultat : le projet apparaît dans GitLab
   (`https://gitlab.192.168.33.100.nip.io/<group>/`), les `Application`
   ArgoCD correspondantes sont visibles et synchronisées (`make status` ou
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

Cette commande enchaine, avec reprise automatique en cas d'échec
(`.bootstrap-state.json`) :

- `make vm-images` : construit puis enregistre les boxes Vagrant `k8s-master`
  et `k8s-worker`.
- `make cluster-from-images` : demarre les VMs et initialise le cluster depuis
  ces boxes.
- `make platform-bootstrap` : installe ArgoCD puis bootstrappe GitLab, le
  runner et les apps plateforme (les images applicatives sont poussées sur
  GHCR, pas sur un registry interne).
- `make ghcr-pull-secret` : depose le secret GHCR source dans le namespace
  `argocd` ; chaque app le recopie ensuite dans ses namespaces via un Job
  genere par `render-argocd-apps.py` a la creation de ses namespaces.
- `make gitlab-git-creds` : cree un PAT GitLab root et l'injecte dans
  `git-credential` pour l'URL interne du cluster.

Les etapes restent executables separement :

```sh
make env
make vm-images
make cluster-from-images
make platform-bootstrap
make ghcr-pull-secret
make gitlab-git-creds
```

Pour rejouer uniquement la séquence complète avec reprise automatique :
`make platform-up` (depuis zéro) ou `make platform-provision` (sans
reconstruire les images Packer existantes).

En cas d'échec pendant le bootstrap plateforme, reprendre à l'étape utile sans
rejouer tout le début :

```sh
make platform-bootstrap START_AT=gitlab-tf-credentials
make platform-bootstrap-from-gitlab-tf-credentials
```

`platform.yml` est un profil operateur local, pas la source de verite des
projets. Toute valeur necessaire a l'autonomie d'un repo doit rester declaree
dans ce repo, puis peut etre surchargee ici pour orchestrer le POC complet.

Les compromis de securite propres au POC sont documentes dans
`docs/security-poc.md`, incluant la gestion des secrets chiffres SOPS
(`secrets/ghcr-pull-secret.yaml`).

## Scripts workspace

Les scripts operateur du workspace sont versionnes dans `scripts/` :

```sh
bash scripts/clone-github-org.sh
bash scripts/commit-push-subprojects.sh --message "..." --remote github
bash scripts/commit-gitlab-app-repos.sh --message "..."
```

Les repos du POC sont maintenant references comme sous-modules Git. Apres un
clone, initialiser le workspace avec :

```sh
git submodule update --init --recursive
```
