# Raccourcis de securite du POC

Ce POC assume un reseau local jetable. Les choix suivants sont acceptes pour
reduire le cout de bootstrap, mais ne doivent pas devenir les valeurs par
defaut d'un environnement partage ou durable.

## TLS auto-signe

GitLab et ArgoCD sont exposes en HTTPS sur `*.nip.io`, avec un certificat
wildcard termine par la Gateway Traefik (`nip-io-wildcard-tls`), emis et
renouvele par cert-manager depuis une CA interne auto-signee (`ClusterIssuer`
`poc-lab-ca-issuer`) — le cycle de vie du certificat est gere, mais la CA
reste auto-signee : le certificat est toujours a accepter dans le navigateur,
et a faire confiance explicitement dans les outils (scripts bootstrap
`GITLAB_INSECURE_TLS=true`, trust store du job `semantic-release`). Pour une
plateforme durable, brancher le `ClusterIssuer` sur une PKI d'entreprise ou
un emetteur ACME public et une policy d'entree explicite.
Les images applicatives sont poussees sur GHCR (TLS public) : pas de registry
interne au cluster a securiser.

## Comptes bootstrap

Les scripts de seed utilisent le compte `root` GitLab ou des tokens de bootstrap.
Les secrets repository ArgoCD (acces aux repos manifests prives) sont fabriques
par External Secrets Operator directement a partir du mot de passe root GitLab
(`gitlab-gitlab-initial-root-password`) — entierement declaratif mais non
scope. Pour une plateforme durable, creer des tokens scopes par usage : seed,
push manifests, lecture ArgoCD (PAT `read_repository` dedie), runner
registration.

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
execute depuis le poste ; `make ghcr-pull-secret` ne fait qu'attendre la
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
Flux lit GitHub) avant `make platform-up` / `make ghcr-pull-secret`. Rejouer
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
