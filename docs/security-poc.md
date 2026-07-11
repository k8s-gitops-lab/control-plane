# Raccourcis de securite du POC

Ce POC assume un reseau local jetable. Les choix suivants sont acceptes pour
reduire le cout de bootstrap, mais ne doivent pas devenir les valeurs par
defaut d'un environnement partage ou durable.

## TLS auto-signe

Depuis la bascule gitlab.com du 2026-07-10 (cf. `docs/backlog.md`), seuls
**ArgoCD et les apps** restent derriere la Gateway Traefik locale, exposes en
HTTPS sur `*.nip.io` avec un certificat wildcard (`nip-io-wildcard-tls`), emis
et renouvele par cert-manager depuis une CA interne auto-signee
(`ClusterIssuer` `poc-lab-ca-issuer`) — le cycle de vie du certificat est
gere, mais la CA reste auto-signee : le certificat est toujours a accepter
dans le navigateur pour ces services-la. Pour une plateforme durable,
brancher le `ClusterIssuer` sur une PKI d'entreprise ou un emetteur ACME
public et une policy d'entree explicite.

**gitlab.com, GHCR et Grafana Cloud sont en TLS public** (pas de CA a
distribuer cote client) : GitLab n'est plus in-cluster, les images
applicatives sont poussees sur GHCR, et les metriques/logs partent vers
Grafana Cloud.

**Traversee du proxy Zscaler d'entreprise** : tout trafic sortant du cluster
vers ces services publics passe par un proxy qui re-signe le TLS avec une CA
d'entreprise (Zscaler) — sans confiance explicite de cette CA, ces flux
echouent en erreur de certificat. La CA est distribuee a chaque composant qui
en a besoin :
- runner CI (`argocd/platform/gitlab-runner-com/values.yaml`,
  `certsSecretName: zscaler-ca-runner-com`) — les jobs recoivent en plus la CA
  via la variable CI `CUSTOM_CA_CERTS` (variable de groupe gitlab.com, cf.
  `gitlab-projects-iac/terraform/main.tf`) pour leurs propres appels sortants
  (ex. push vers Grafana Cloud dans `ci-templates`) ;
- tf-controller (`argocd/platform/tf-controller/zscaler-ca-configmap.yaml`,
  monte dans le pod runner Terraform via `SSL_CERT_FILE`, cf.
  `terraform-gitlab-com.yaml`) — necessaire pour que le provider `gitlab_*`
  atteigne l'API gitlab.com ;
- ClusterExternalSecret Grafana Cloud
  (`argocd/platform/grafana-cloud-secret/external-secret.yaml`) — meme CA
  pour joindre `*.grafana.net`.

## Comptes et tokens en circulation

Plus de compte `root` GitLab ni de mot de passe root fabrique par un script
(mecanisme et secret `gitlab-gitlab-initial-root-password` supprimes avec
l'instance locale). L'inventaire reel des tokens, en circulation sur ce POC :

| Token | Scope | Stocke dans | Usages |
|---|---|---|---|
| PAT operateur gitlab.com (`GITLAB_TOKEN`) | `api` (proprietaire du groupe) | git-credential local (poste operateur), variable de groupe `GITLAB_PUSH_TOKEN` (meme valeur, `gitlab-projects-iac/terraform/main.tf`), secret SOPS `flux-secrets/gitlabcom-credentials.yaml` (cle `gitlab_token`, utilise par le CR Terraform `gitlab-iac-com` et par le `ClusterSecretStore gitlabcom-secrets` pour les repo-creds ArgoCD) | `gitlab-reset.py`, `gitlab-tf-state-seed.py`, `gitlab-git-creds.py`, push des manifests par le pipeline `deploy-gitops` (`GITLAB_PUSH_TOKEN`), apply Terraform gitlab.com |
| PAT GitHub (`GITHUB_TOKEN`) | `repo` | secret SOPS `flux-secrets/github-credentials.yaml`, variable de groupe `GHCR_TOKEN` (meme valeur, pull GHCR) et `GITHUB_TOKEN` du groupe `infra` (CI `platform-gitops`, push `onboard-apps`) | import initial des projets GitLab depuis GitHub (`import_url`), pull d'images GHCR par les runners, push automatique des manifests generes vers GitHub par la CI de `platform-gitops`, `gitlab-tf-state-seed.py` |

**Rayon d'explosion** : un seul PAT proprietaire scope `api` couvre tout
gitlab.com (reset, seed, credentials git, variable de groupe) — sa
compromission expose l'integralite du groupe `k8s-gitops-lab`. Pas de token
scope par projet ni de compte de service dedie (gitlab.com Free ne permet pas
`gitlab_group_access_token` a ce compte, 400 constate — cf.
`gitlab-projects-iac/terraform/main.tf`). Dette assumee et suivie a l'axe 7
du backlog (tokens scopes par projet).

## CA corporate

Le bootstrap ArgoCD injecte une CA locale depuis le trousseau macOS. Pour une
plateforme durable, gerer la CA comme un secret/config declare, versionne selon
le niveau de sensibilite, et applique par GitOps.

## Gestion des secrets sensibles — SOPS + age

Les credentials qui ne doivent pas apparaitre en clair dans git (tokens de
service, secrets `dockerconfigjson`) sont stockes dans
`platform-gitops/flux-secrets/` sous forme de fichiers SOPS chiffres avec
`age` — par exemple `flux-secrets/ghcr-pull-secret.yaml`, dechiffre dans le
cluster par la Kustomization Flux `flux-secrets` (cle privee injectee dans le
secret `sops-age` par le bootstrap). Aucun dechiffrement `kubectl` n'est
execute depuis le poste ; `make ghcr-pull-secret-wait` ne fait qu'attendre la
convergence.

### Structure (dans platform-gitops)

```
.sops.yaml                  # règle de chiffrement (commité)
flux-secrets/*.yaml         # fichiers chiffrés (commités, appliqués par Flux)
~/.config/sops/age/keys.txt # clé privée age (JAMAIS commitée)
```

### Prérequis

```bash
brew install age sops
```

### Premier parametrage (nouvel operateur) : `make ghcr-token-init`

Chaque operateur du POC travaille avec sa propre cle age locale :
`platform-gitops/.sops.yaml` ne declare qu'un seul recipient a la fois, celui
de l'operateur courant. En clonant le workspace, remplacer ce recipient et
regenerer le secret GHCR se fait en une commande :

```bash
make ghcr-token-init
```

Cette commande (`scripts/ghcr-token-init.py`) :

1. Genere `~/.config/sops/age/keys.txt` si absente (reutilisee sinon).
2. Enregistre la cle publique correspondante comme recipient dans
   `platform-gitops/.sops.yaml`.
3. Demande un compte GitHub et un PAT (scope `read:packages`, saisie masquee) —
   un lien de creation rapide du token est affiche.
4. Construit et chiffre `platform-gitops/flux-secrets/ghcr-pull-secret.yaml`
   (seul `stringData` est chiffre, via
   `--encrypted-regex '^(stringData|data)$'`).
5. Verifie que le secret est bien dechiffrable avec la cle locale.

A l'issue de la commande, committer/pousser `.sops.yaml` et
`flux-secrets/ghcr-pull-secret.yaml` dans `platform-gitops` (sur `origin` :
Flux lit GitHub) avant `make platform-up` / `make ghcr-pull-secret-wait`. Rejouer
la commande plus tard permet de faire tourner (rotate) le token GitHub sans
toucher a la cle age — External Secrets propage la rotation aux namespaces
applicatifs sans autre action. Attention : changer de cle age rend les autres
fichiers `flux-secrets/*.yaml` (ex. `github-credentials.yaml`) indechiffrables
par Flux tant qu'ils ne sont pas re-generes avec la nouvelle cle.

### Modifier un secret manuellement

Pour les autres secrets `flux-secrets/*.yaml`, ou pour editer
`ghcr-pull-secret.yaml` sans repasser par le script (depuis `platform-gitops`) :

```bash
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt sops flux-secrets/ghcr-pull-secret.yaml
```

SOPS ouvre l'editeur avec le contenu dechiffre. A la fermeture, le fichier est
re-chiffre automatiquement.

### Lire une valeur manuellement

```bash
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt \
  sops --decrypt --extract '["stringData"][".dockerconfigjson"]' flux-secrets/ghcr-pull-secret.yaml
```

### Ce qui est commité / non commité

| Fichier | Commité | Raison |
|---|---|---|
| `platform-gitops/.sops.yaml` | oui | contient uniquement la clé publique |
| `platform-gitops/flux-secrets/*.yaml` | oui | chiffré par SOPS, illisible sans la clé privée |
| `~/.config/sops/age/keys.txt` | non | clé privée, à sauvegarder hors git |

Pour une plateforme durable, centraliser la clé dans un gestionnaire de secrets
(Vault, AWS Secrets Manager) et remplacer `age` par le KMS correspondant.
