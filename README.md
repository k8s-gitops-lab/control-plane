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

## Usage

```sh
make env
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
