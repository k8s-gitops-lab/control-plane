# control-plane

Point d'entree operateur optionnel du POC.

Ce repo ne remplace pas les repos existants et ne doit pas devenir une
dependance d'execution pour eux. Chaque projet reste autonome : ses Makefiles,
valeurs par defaut et procedures doivent continuer a fonctionner depuis son
propre repo.

`control-plane` fournit seulement un profil local pour enchaîner les commandes
des repos specialises avec des variables explicites :

- `cluster` : socle Kubernetes, storage, Gateway API, MetalLB, Traefik.
- `platform-cicd` : bootstrap ArgoCD, GitLab, registry et runner.
- `platform-gitops` : configuration suivie en continu par ArgoCD.
- `toolbox` : seed GitLab, credentials ArgoCD et onboarding.

La vue globale du projet vit ici :

- `docs/repo-map.md` : role de chaque repo du workspace.
- `docs/source-control.md` : separation GitHub amont vs GitLab runtime.
- `docs/prd.md` : intention, périmètre et limites du POC.
- `docs/spec-fonctionnelle.md` : flow Git, CI/CD et parcours applicatif.
- `docs/spec-technique.md` : détails d'implémentation et contraintes infra.
- `docs/prod-constraints.md` : contraintes à prévoir pour une cible prod.

## Usage

Parcours complet avec images VM Packer :

```sh
make platform-up
```

Cette commande enchaine :

- `make vm-images` : construit puis enregistre les boxes Vagrant `k8s-master`
  et `k8s-worker`.
- `make cluster-from-images` : demarre les VMs et initialise le cluster depuis
  ces boxes.
- `make platform-bootstrap` : installe ArgoCD puis bootstrappe GitLab, le
  registry, le runner et les apps plateforme.

Les etapes restent executables separement :

```sh
make env
make vm-images
make cluster-from-images
make platform-bootstrap
```

Le chemin historique sans images Packer reste disponible :

```sh
make cluster-up
make platform-bootstrap
make gitlab-seed
make argocd-repo-creds
```

`platform.yml` est un profil operateur local, pas la source de verite des
projets. Toute valeur necessaire a l'autonomie d'un repo doit rester declaree
dans ce repo, puis peut etre surchargee ici pour orchestrer le POC complet.

Les compromis de securite propres au POC sont documentes dans
`docs/security-poc.md`.

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
