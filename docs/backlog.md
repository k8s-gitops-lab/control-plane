# Backlog produit

> Backlog général du produit (généralisé le 2026-07-09, en application de la
> règle « Gouvernance du développement » d'`AGENTS.md`). Les **idées
> produit** passent ici *avant* implémentation ; les **correctifs** et
> l'entretien s'y tracent au plus tard au moment du commit — pas de fiche
> préalable exigée pour un bug réglé en séance. Chaque tâche est
> implémentée **dans son repo propriétaire**,
> jamais depuis `cockpit` (cf. `AGENTS.md`). Deux volets : l'initiative
> extensibilité (sections « Axe N » ci-dessous) et l'entretien courant
> (section en fin de fichier).

## Initiative extensibilité / généricité

> Initiative transverse décidée le 2026-07-08 : rendre le produit plus
> extensible et instanciable ailleurs (autre domaine, autre registre,
> plusieurs équipes). L'état ci-dessous a été vérifié sur le code —
> plusieurs axes sont déjà partiellement en place. Les fiches de tâches
> détaillées (`docs/tasks-extensibilite.md`) et le pense-bête `TODO.txt` ont
> été supprimés le 2026-07-08 car redondants avec ce fichier ; les points
> clés (pièges, critères de vérification, dette transverse) ont été repliés
> dans les sections ci-dessous. Cette partie du fichier est l'unique support
> de suivi de l'initiative.

## Tableau de suivi

| # | Axe | Statut | Repo(s) propriétaire(s) | Risque |
|---|---|---|---|---|
| 1 | Schéma d'inventaire versionné + validation CI | ✅ Fait | `platform-gitops` (+ `platform-bootstrap`) | Faible |
| 2 | Contrat de variables plateforme (dé-duplication domaine/registre) | Partiel | `platform-gitops`, `gitlab-projects-iac`, `ci-templates`, `infra-iac` | Faible |
| 3 | Générateur natif ArgoCD (réduire `render-argocd-apps.py`) | Partiel | `platform-bootstrap`, `platform-gitops` | Élevé (spike) |
| 4 | `ci-templates` → composants CI versionnés (`spec:inputs`) | ✅ Fait | `ci-templates` | Moyen |
| 5 | Séquence d'environnements déclarée par app | Partiel | `platform-gitops` + `ci-templates` | Moyen-élevé |
| 7 | Multi-tenancy GitLab (token de projet par app) | Partiel | `gitlab-projects-iac`, `platform-bootstrap` | Élevé (sécurité) |
| 6 | Scaffolding d'app (`app-template` + `toolbox`) | **Différé** | `toolbox` (+ nouveau repo) | — |

## Séquencement recommandé

1. **Phase 1 — fondations (faible risque)** : axe 1 puis axe 2. Contrat
   d'entrée (schéma) + contrat de sortie (variables) ; ils dé-risquent tout
   le reste.
2. **Phase 2 — refactor CI** : axe 4 est déjà fait (composants versionnés en
   place). Reste seulement axe 5 (séquence déclarative) à faire, sur les
   composants existants — notamment généraliser `deploy-gitops` pour
   générer un job par environnement déclaré au lieu de 4 jobs figés.
3. **Phase 3 — spikes** : axe 3 (générateur natif) et axe 7 (tokens de
   projet), chacun précédé d'une spike de validation.
4. **Différé** : axe 6.

---

## Axe 1 — Schéma d'inventaire versionné

**État actuel** : aucun schéma formel. Le contrat vit implicitement dans
`platform-bootstrap/scripts/platform_inventory.py` (`_normalize_app`). Champs
requis : `name`, `group`. Tout le reste est dérivé par convention :
`description`, `services` (liste de strings ou `{name,image}`), `hasPreprod`,
`environments`, `manifests`, `code`, `showcaseService`, `argocd`,
`importFromGithub`.

**Reste à faire** : ~~JSON Schema versionné + job de validation CI~~ — **fait**
(2026-07-08, `platform-gitops`) : `argocd/apps.schema.json` (draft 2020-12,
`apiVersion: platform/v1`, requis `name`+`group`, `additionalProperties:false`),
`scripts/validate-inventory.py`, job CI `validate-inventory` sur MR + main.
`helloworld.yaml` estampillé `apiVersion` (zéro impact rendu, vérifié via
`render --check`). Suite possible : faire dériver `_normalize_app` du schéma
pour garantir la non-dérive, et étendre le schéma quand l'axe 5 arrive.

## Axe 2 — Contrat de variables plateforme

**État actuel (partiel, affiné le 2026-07-08)** : `platform-gitops/argocd/
apps.yaml` porte déjà un bloc `platform:` (`domain`, `repoURL`,
`targetRevision`, `registry.host`) + `gitlab.internalHost`, et
`platform_constants()` (Python) fusionne déjà ce bloc par-dessus
`_PLATFORM_DEFAULTS` — `apps.yaml` gagne quand présent, ce n'est pas une
duplication aveugle. `ci-templates` a migré vers des composants CI/CD
versionnés (voir axe 4, fait) : `registry_host` y est déjà un `spec:inputs`
typé, `INTERNAL_GITLAB_HOST` reste délibérément une `variables:` (décision
documentée). Le vrai trou confirmé : **`DOMAIN`** est consommé par
`ci-templates/templates/deploy-gitops/template.yml` (`environment.url`)
mais **aucune `gitlab_group_variable DOMAIN`** n'existe dans
`gitlab-projects-iac` pour l'alimenter en pipeline réel. `gitlab_url` (TF)
est bien utilisé par `providers.tf`, mais sa valeur effective vient du CR
Flux `terraform-gitlab.yaml` qui la hardcode (4ᵉ emplacement du domaine).
Le domaine `192.168.33.100.nip.io` reste en dur dans 38 fichiers de 8 repos
au total (revérifié le 2026-07-08 ; `infra-iac` n'en a aucun).

**Reste à faire** : (2a, prioritaire) créer `gitlab_group_variable DOMAIN`
par groupe d'app dans `gitlab-projects-iac/terraform/main.tf`, en suivant le
pattern `for_each = local.app_groups` déjà en place — c'est le canal natif
manquant, aucun changement requis côté `ci-templates` (qui lit déjà
`${DOMAIN}`). Dédupliquer `_PLATFORM_DEFAULTS`/`platform_constants()` entre
`platform-bootstrap` et `toolbox`. (2b, plus lourd) câbler le CR Flux
`terraform-gitlab.yaml` sur `apps.yaml.platform.domain`, et paramétrer les
hostnames d'ingress des manifests plateforme statiques. Chaque repo garde
son default local (cf. `AGENTS.md`) ; le contrat ne fixe que les noms.
Objectif : instancier le produit ailleurs sans grep multi-repo.

**Pièges** : les `_PLATFORM_DEFAULTS` sont un filet de sécurité, pas un
doublon à supprimer aveuglément. Les manifests plateforme (2b) sont
consommés tels quels par ArgoCD : une substitution non résolue casse le
déploiement — tester sur un env jetable. Vérification : `grep -rln
'192.168.33.100'` avant/après (le compte de consommateurs baisse),
`render-argocd-apps.py --check` inchangé, `terraform validate`.

## Axe 3 — Générateur natif ArgoCD

**État actuel (partiel, revérifié le 2026-07-08)** : il existe déjà un
`ApplicationSet` avec un git *directory* generator sur
`argocd/generated/apps/*`, mais ces répertoires sont produits par une étape
de rendu (`render-argocd-apps.py`, 310 lignes — a grossi depuis la rédaction
initiale, probablement lié à la validation d'inventaire de l'axe 1, génère
aussi namespaces, ExternalSecrets, AppProjects).

**Reste à faire (spike)** : évaluer un git *files* generator consommant
directement `argocd/apps/*.yaml` + `goTemplate`, pour supprimer/réduire le
rendu. Point dur : ExternalSecrets, namespaces et projets sont aussi générés
— la spike doit trancher ce qui devient natif vs ce qui reste scripté.

**Pièges** : la dérivation par convention (`_normalize_app`) est riche
(services→images, hosts, `argocdRepoURL` in-cluster) — `goTemplate` doit
reproduire cette logique ou l'inventaire doit porter plus de champs, sinon
la complexité se déplace au lieu de se réduire. Documenter le verdict
(natif vs scripté) avant d'implémenter.

## Axe 4 — Composants CI versionnés [FAIT]

**État actuel (revérifié le 2026-07-08)** : déjà implémenté. `ci-templates/
gitlab-ci.yml` n'existe plus — le repo expose 3 composants versionnés
(`templates/{build-docker,deploy-gitops,promote}/template.yml`), chacun avec
`spec:inputs` typés (defaults, regex). `build-docker` construit via Buildah
(ni Docker ni Kaniko malgré son nom — cf. commentaire `stages:` de
`helloworld/.gitlab-ci.yml`). `helloworld/.gitlab-ci.yml` consomme déjà
`include:component@v3.0.0` avec un bloc `inputs:` par composant, sans
aucune logique inline.

**Reste à faire (optionnel)** : rien de bloquant. `deploy-gitops` génère
encore 4 jobs figés (`deploy-{dev,rec,preprod,prod}`) — la rendre
générique par environnement déclaré est le travail de l'axe 5, pas de
celui-ci. Vérifier si un catalogue CI/CD formel apporterait un bénéfice
réel vs le mécanisme `include:component` par chemin de projet, qui
fonctionne déjà sans lui.

## Axe 5 — Séquence d'environnements déclarée par app

**État actuel (partiel)** : `_normalize_app` accepte déjà un champ
`environments:` qui surcharge intégralement la séquence dérivée
(`dev/rec/preprod?/prod`), et `hasPreprod` bascule preprod. MAIS le
composant `ci-templates/templates/deploy-gitops/template.yml` (chemin mis à
jour — repo réorganisé en composants versionnés, cf. axe 4, fait) câble en
dur les jobs `deploy-dev/rec/preprod/prod` avec une gate `HAS_PREPROD` — la
séquence n'est donc PAS réellement déclarative côté CI.

**Reste à faire** : permettre de déclarer la séquence par app (ex.
`environments: [dev, staging, prod]` en noms, le reste dérivé) et la
consommer **des deux côtés** : rendu ArgoCD ET génération des jobs de
déploiement (couplé à l'axe 4, via un composant qui génère un job par env
déclaré). `preprod` cesse d'être un cas spécial → juste un env de la liste.

**Pièges** : garder `helloworld.yaml` (`hasPreprod: true`) rétro-compatible,
ou migrer explicitement vers `environments:`. La convention `prod → main`
(branche) doit être préservée. Le rendu ArgoCD et la CI doivent lire **la
même** définition d'ordre (source unique : l'entrée d'inventaire).

## Axe 7 — Multi-tenancy GitLab

**État actuel (partiel)** : le champ `group` existe déjà par app dans
l'inventaire ET dans `gitlab-projects-iac/terraform/variables.tf` ; les
projets sont créés sous ce groupe.

**Reste à faire** : remplacer le token personnel `root` partagé (scope `api`
complet, rayon d'explosion maximal — déjà signalé comme dette dans le PRD)
par un **token de projet** (`project access token`) par couple
`<app>`/`<app>-iac`, scopé au strict nécessaire. Touche `gitlab-projects-iac`
(création des tokens) et le plumbing de secrets CI.

**Pièges** : un *project bot* issu d'un access token ne peut pas être
ajouté à un autre groupe/projet (limitation GitLab documentée dans les
commentaires Terraform) — contraint la conception cross-groupe, notamment
l'accès en lecture à `shared-ci/ci-templates` depuis le token d'une app
d'un autre groupe. Les project access tokens expirent : prévoir une
stratégie de rotation, sinon la CI casse silencieusement.

---

## Différé

### Axe 6 — Scaffolding d'app (`app-template`)

Repo `app-template` (cookiecutter via `toolbox`) générant `<app>` +
`<app>-iac` + `.gitlab-ci.yml` + l'entrée d'inventaire, pour réduire
l'onboarding à une commande + une MR et garantir que les nouvelles apps
naissent conformes au pattern. **À traiter un autre jour** (décision
2026-07-08).

---

## Observabilité SaaS (Grafana Cloud)

> Décidé le 2026-07-10 : `docs/prod-constraints.md` liste depuis le début
> l'absence de centralisation logs/métriques comme un gap ("Centralize
> logs", "Collect metrics with alerting, not only dashboards"). L'opérateur
> a un stack Grafana Cloud existant (SaaS) et souhaite y brancher le lab
> plutôt que d'auto-héberger Prometheus Operator/Loki/Tempo — cohérent avec
> le choix déjà fait pour GHCR (registre externe plutôt qu'interne au
> cluster).

**Périmètre** : metrics + logs + traces via Grafana Alloy (chart
`grafana/k8s-monitoring`), push sortant uniquement (compatible avec
l'absence d'exposition Internet entrante du lab, cf.
`spec-technique.md`). Autodiscovery des pods par annotations
`k8s.grafana.com/scrape` (pas de CRD Prometheus Operator introduite). Les
traces sont plombées bout-en-bout côté infra (réception OTLP) mais aucune
app n'émet de spans dans ce lot — seule l'instrumentation métriques est
faite. Logs de tous les pods du cluster collectés sans annotation requise
(`podLogsViaLoki`), donc `helloworld` en bénéficie déjà nativement sur ses
4 environnements — complété par des logs structurés JSON côté app et un
label `app.kubernetes.io/name` pour un `service_name` Loki propre.

Le trafic sortant de ce cluster passe par une inspection TLS d'entreprise
(Zscaler) : la CA correspondante (même certificat que
`helloworld-svc/certs/zscaler-root-ca.crt`) a dû être injectée dans le
secret consommé par Alloy, sans quoi tout push vers `*.grafana.net`
échouait silencieusement ou en erreur selon le composant.

**Repos propriétaires** :
- `platform-gitops` : add-on plateforme (`argocd/managed/
  grafana-k8s-monitoring.yaml`, secret SOPS + `ExternalSecret`), suit le
  pattern existant (GitLab, External Secrets).
- `helloworld` : instrumentation métriques HTTP de `helloworld-svc`
  (`axum-prometheus`, route `/metrics`) + logs structurés JSON
  (`tracing`/`tracing-subscriber`/`tower-http`).
- `helloworld-iac` : annotations de scrape + label `app.kubernetes.io/name`
  sur les `Deployment` `helloworld-svc`/`helloworld-gui`.

**Statut** : fait (2026-07-10) pour metrics+logs ; traces plombées côté
infra mais sans app instrumentée (suite possible, non planifiée).

---

## Migration GitLab self-hosted → GitLab.com (SaaS)

> Décidé le 2026-07-10 : l'opérateur n'a pas de compte GitLab payant, mais
> les runners self-hosted ne consomment pas le quota CI/CD du plan Free
> (seuls les runners SaaS partagés sont limités en minutes) — pas de
> blocage identifié pour ce lab mono-opérateur. Bénéfice induit : gitlab.com
> a un certificat TLS public, ce qui supprime le contournement CA
> auto-signée/Zscaler nécessaire aujourd'hui pour tout accès HTTPS au
> GitLab local (cf. section Observabilité ci-dessus pour le même problème
> côté Grafana Cloud) et le miroir local `to-be-continuous` (gitlab.com
> résout `include:component` nativement, cf. `repo-map.md`).

**Périmètre** : tous les repos du workspace passent en double hébergement
GitHub (`origin`, déjà en place) + GitLab.com (`gitlab`, remplace
l'instance locale `gitlab.192.168.33.100.nip.io`) en mode mirroring. Le
Runner CI/CD reste self-hosted dans le cluster local (executor Kubernetes,
arm64 préservé) mais s'enregistre contre gitlab.com au lieu du GitLab
in-cluster. Le GitLab in-cluster (chart Helm, Application ArgoCD
`platform-gitops/argocd/managed/gitlab.yaml`) est décommissionné en fin de
migration, pas en début — bascule progressive, pas un big bang.

**Cartographie des dépendances actuelles au GitLab in-cluster** (établie le
2026-07-10, cf. repos cités) :
1. **SSO ArgoCD** : connector Dex `type: gitlab` (`platform-gitops/argocd/
   platform/argocd-config/argocd-cm.yaml`) pointe sur le GitLab local ;
   l'Application OAuth est créée par
   `platform-bootstrap/scripts/gitlab-dex-oauth-app.py` (auth root). Sur
   gitlab.com il n'existe pas de mot de passe root exploitable par script :
   l'Application OAuth devra être créée une fois manuellement (ou via PAT).
2. **Terraform `gitlab-projects-iac`** : déjà authentifié par PAT
   (`providers.tf`), pas par le root token directement — seul `gitlab_url`
   (`variables.tf`, défaut local, `insecure = true`) et la génération du
   PAT (`platform-bootstrap/scripts/gitlab-tf-credentials.py`, via root)
   changent.
3. **Runner** : sous-chart `gitlab-runner` du chart GitLab lui-même
   (`platform-gitops/argocd/platform/gitlab/values-local.yaml`), token créé
   par `platform-bootstrap/scripts/gitlab-runner-token.py`
   (`POST /api/v4/user/runners`, instance-wide token) — sur gitlab.com
   l'enregistrement se fait pareil via API avec un PAT, mais le runner doit
   devenir un chart/Application autonome (il ne peut plus vivre en
   sous-chart du GitLab qu'on décommissionne).
4. **Repo credentials ArgoCD** : `platform-gitops/argocd/generated/apps/
   helloworld/repo-creds.yaml` lit le mot de passe **root** du GitLab local
   via `ClusterSecretStore` `gitlab-secrets` — mécanisme entièrement à
   remplacer par un PAT dédié (recoupe l'axe 7 ci-dessus : same idée que
   "token de projet" plutôt que credentials root partagées, périmètre élargi
   par cette migration).
5. **Bootstrap sequencing** : `platform-bootstrap/ansible/roles/
   platform_bootstrap/tasks/main.yml` enchaîne les 3 scripts Python
   `gitlab-*` après `wait_for_gitlab_ready` sur l'instance locale — la
   logique d'attente disparaît (gitlab.com est toujours prêt), mais l'ordre
   (credentials → Dex → runner) reste probablement valable.
6. **Miroir `to-be-continuous`** : entièrement porté par
   `gitlab-projects-iac/terraform/main.tf` (groupe + projets
   `import_url`), recréable tel quel sur gitlab.com — mais devient inutile
   dès que `ci-templates` résout les composants directement sur
   `gitlab.com/to-be-continuous` (variable prédéfinie `$CI_SERVER_FQDN`,
   déjà agnostique de l'instance).
7. **Registry interne** : déjà désactivé (`registry.enabled: false`),
   aucun impact — GHCR reste le registre.

**Repos impactés** (constat 2026-07-10, détail par phase à affiner lors du
séquencement) : `gitlab-projects-iac` (provider Terraform, groupe miroir),
`platform-bootstrap` (3 scripts `gitlab-*`, séquence Ansible),
`platform-gitops` (Dex config, repo-creds, retrait à terme de
`argocd/managed/gitlab.yaml` + `gitlab-routes` + `gitlab-minio-patch`),
`ci-templates` (retrait possible du miroir), `cockpit` (Makefile,
`scripts/gitlab-git-creds.py`, docs `source-control.md`/`repo-map.md`),
`infra-iac`/`helloworld`/`helloworld-iac` (docs mentionnant l'URL locale).

**Risque** : élevé — touche l'authentification ArgoCD (SSO), les credentials
Terraform et les credentials repo GitOps simultanément ; pas de session
utilisateur payante pour valider certains comportements SaaS avant coupure.
Bascule à faire en parallèle (nouveau flux gitlab.com validé avant retrait
de l'ancien), pas en remplacement direct.

**Statut** : Phase 1 (structure minimale + validation du mirroring) faite le
2026-07-10 : module `gitlab-projects-iac/terraform-gitlabcom/` appliqué
(groupe racine `k8s-gitops-lab` public — création manuelle puis import,
création de groupe top-level bloquée via API sur ce compte — + sous-groupes
`infra`/`shared-ci`/`hello-groupe` + 4 projets vides) ; remote `gitlabcom`
ajouté et poussé avec succès sur les 4 repos concernés
(`platform-gitops`, `ci-templates`, `helloworld`, `helloworld-iac`) —
`main` == `gitlabcom/main` vérifié sur les quatre. Volontairement minimal
(pas de variables CI/CD, pas de branch protection, pas d'utilisateur de
service, pas de `gitlab_project_mirror`, cf. commentaire du module).

**Reste à faire (phases suivantes, séquencement à détailler)** : les 7
points de la cartographie de dépendances ci-dessus restent entiers (SSO
Dex, PAT Terraform, runner, repo-creds ArgoCD, séquencement bootstrap,
miroir `to-be-continuous`, registry) — Phase 1 ne fait que prouver que le
push fonctionne, elle ne bascule aucun consommateur réel du GitLab local.

---

## Entretien courant

Tâches hors initiative : montées de version, pins d'images, correctifs de
fond. Les montées de version des composants font partie de l'entretien
normal de la plateforme (cf. `AGENTS.md`).

- [ ] Revue de gouvernance trimestrielle (prochaine : 2026-10) — rejouer la
  revue des trois axes d'`AGENTS.md` : PRD vs réalité, complexité du code,
  `repo-map.md` vs dépendances réelles, fraîcheur des composants. Première
  revue faite le 2026-07-09 (4 écarts corrigés).
- [ ] Activer Dependabot (ou Renovate) sur l'org GitHub `k8s-gitops-lab`
  pour signaler les montées de version (Dockerfiles, charts Helm) — le
  signal alimente cette section ; sans lui, « versions récentes » ne se
  produit pas tout seul.
- [ ] Pinner et rafraîchir les images MinIO du chart GitLab (reporté le
  2026-07-09) — repo `platform-gitops` : `minio/minio` et `minio/mc` sans
  tag dans `argocd/platform/gitlab/values-local.yaml`, et
  `minio/mc:RELEASE.2022-09-16T09-16-47Z` (4 ans) dans
  `argocd/platform/gitlab-minio-patch/`. Vérifier au passage si le chart
  GitLab récent permet de se passer du patch minio.
- [x] Pinner les images applicatives de `helloworld` (fait le 2026-07-09) :
  `rust:1.88-slim` → `rust:1.96-slim-bookworm` (aligné glibc avec le runtime
  `debian:bookworm-slim`), `nginx:alpine` → `nginx:1.31-alpine`.

## Dette transverse

- [x] Repousser tous les commits en attente vers le remote `gitlab` — fait
  le 2026-07-09 (GitLab de nouveau joignable) : `helloworld`,
  `helloworld-iac` et `platform-gitops` poussés, `ci-templates` déjà à jour.

(Les autres points de dette relevés — dérivation de `_normalize_app` depuis
le JSON Schema, `gitlab_group_variable DOMAIN` manquante — sont déjà suivis
respectivement dans les sections Axe 1 et Axe 2 ci-dessus.)
