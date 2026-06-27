# control-plane

Point d'entree operateur optionnel du POC.

Ce repo ne remplace pas les repos existants et ne doit pas devenir une
dependance d'execution pour eux. Chaque projet reste autonome : ses Makefiles,
valeurs par defaut et procedures doivent continuer a fonctionner depuis son
propre repo.

`control-plane` fournit seulement un profil local pour enchaîner les commandes
des repos specialises avec des variables explicites :

- `../cluster` : socle Kubernetes, storage, Gateway API, MetalLB, Traefik.
- `../platform-cicd` : ArgoCD, GitLab, registry, runner et apps platform.
- `../toolbox` : seed GitLab, credentials ArgoCD et onboarding.

La vue globale du projet vit ici :

- `docs/prd.md` : intention, périmètre et limites du POC.
- `docs/spec-fonctionnelle.md` : flow Git, CI/CD et parcours applicatif.
- `docs/spec-technique.md` : détails d'implémentation et contraintes infra.

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
```

Par defaut, ils ciblent le dossier parent de `control-plane`, c'est-a-dire le
workspace qui contient les repos freres.
