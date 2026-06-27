# Raccourcis de securite du POC

Ce POC assume un reseau local jetable. Les choix suivants sont acceptes pour
reduire le cout de bootstrap, mais ne doivent pas devenir les valeurs par
defaut d'un environnement partage ou durable.

## HTTP interne

GitLab, ArgoCD et le registry sont exposes en HTTP sur `*.nip.io`.
Pour une plateforme durable, remplacer par HTTPS, certificats geres et policy
d'entree explicite.

## Registry insecure

Les jobs Kaniko utilisent `--insecure` et `--skip-tls-verify` pour pousser vers
le registry interne. Pour une plateforme durable, installer une CA de confiance
dans les runners et retirer ces options.

## Comptes bootstrap

Les scripts de seed utilisent le compte `root` GitLab ou des tokens de bootstrap.
Pour une plateforme durable, creer des tokens scopes par usage : seed, push
manifests, lecture ArgoCD, runner registration.

## CA corporate

Le bootstrap ArgoCD injecte une CA locale depuis le trousseau macOS. Pour une
plateforme durable, gerer la CA comme un secret/config declare, versionne selon
le niveau de sensibilite, et applique par GitOps.
