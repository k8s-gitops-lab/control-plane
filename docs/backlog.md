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
1. **SSO ArgoCD** : ~~connector Dex `type: gitlab`~~ — **décidé le
   2026-07-10 : hors périmètre, décommissionné plutôt que migré.** Pas de
   besoin avéré de SSO pour ce lab mono-opérateur ; le login local ArgoCD
   (`admin`) suffit. Retrait complet (pas de remplacement gitlab.com) :
   connector dans `platform-gitops/argocd/platform/argocd-config/
   argocd-cm.yaml`, mapping RBAC associé dans `argocd-rbac-cm.yaml`,
   provisioning `platform-bootstrap/scripts/gitlab-dex-oauth-app.py` +
   tâche Ansible + cible Make, patch CA dédié
   (`platform-bootstrap/argocd/dex-ca-patch.yaml` + tâche de confiance CA
   associée), et l'exposition Gateway dédiée (`platform-gitops/argocd/
   platform/argocd-ui/dex-route.yaml` + `dex-service.yaml`, redondante avec
   le proxy `/api/dex/*` déjà fourni par `argocd-server`).
2. **Terraform `gitlab-projects-iac`** : déjà authentifié par PAT
   (`providers.tf`), pas par le root token directement — seul `gitlab_url`
   (`variables.tf`, défaut local, `insecure = true`) et la génération du
   PAT (`platform-bootstrap/scripts/gitlab-tf-credentials.py`, via root)
   changent.
3. **Runner** : sous-chart `gitlab-runner` du chart GitLab lui-même
   (`platform-gitops/argocd/platform/gitlab/values-local.yaml`), token créé
   par `platform-bootstrap/scripts/gitlab-runner-token.py`
   (`POST /api/v4/user/runners`, `runner_type: instance_type` — requiert
   d'être admin de l'instance GitLab). Validé le 2026-07-10 : sur gitlab.com
   `instance_type` échoue (pas admin de l'instance SaaS) — il faut
   `runner_type: group_type` + `group_id` (le PAT, propriétaire du groupe
   `k8s-gitops-lab`, id `137124101`, suffit), testé en aller-retour
   création/suppression via l'API (`POST`/`DELETE /api/v4/user/runners`),
   jeton `glrt-…` obtenu puis le runner de test supprimé — aucune ressource
   laissée derrière. Reste à faire : sortir `gitlab-runner` en
   chart/Application autonome (il ne peut plus vivre en sous-chart du
   GitLab qu'on décommissionne), avec le tuning arm64/sécurité actuel
   (`helper_image` arm64, `build_container_security_context.run_as_user:
   0`, limites CPU/mémoire) à reporter tel quel — periemètre non trivial,
   pas encore implémenté.
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

**Phase 2 (PAT + Terraform gitlab.com géré par GitOps)** faite le
2026-07-10 : PAT `terraform-controller` créé manuellement par l'opérateur
sur gitlab.com (pas d'automatisation root possible côté SaaS, contrairement
à `gitlab-tf-credentials.py` sur l'instance locale), stocké chiffré SOPS
dans `platform-gitops/flux-secrets/gitlabcom-credentials.yaml`. Nouveau
`Terraform` CR `gitlab-iac-com` (`platform-gitops/argocd/platform/
tf-controller/terraform-gitlab-com.yaml`), backend distinct
(`secretSuffix: gitlab-projects-iac-com`) pour ne pas toucher au CR
`gitlab-iac` existant (instance locale). Le state de l'apply manuel Phase 1
a été **importé** dans le secret backend du controller (`tfstate-default-
gitlab-projects-iac-com`, pré-seedé à partir du `terraform.tfstate` local
avant le premier plan) pour éviter que tofu-controller ne tente de
recréer le groupe/projets déjà existants. Premier plan vérifié « sans
changement », puis bascule en `approvePlan: auto` — `gitlab-iac-com` se
comporte maintenant comme `gitlab-iac`, en parallèle, sans rien retirer
côté local.

**Phase 3 (repo-creds ArgoCD, validation isolée)** faite le 2026-07-10 :
secret repository ArgoCD `gitlabcom-helloworld-iac-repo` (namespace
`argocd`, même forme que `gitlab-helloworld-iac-repo` généré localement
par l'`ExternalSecret`) créé dans `flux-secrets/` et pointé sur
`https://gitlab.com/k8s-gitops-lab/hello-groupe/helloworld-iac.git` via le
PAT. Connectivité vérifiée directement en git (`git ls-remote` avec les
mêmes credentials oauth2/PAT que le secret) : HEAD == `gitlabcom/main`
(`41028ca`), comme déjà validé en Phase 1. Purement additif —
`argocd/generated/apps/helloworld/app-data.yaml` (source réelle des
Applications ArgoCD `helloworld`, dérivée par convention depuis
`argocd/apps/helloworld.yaml`, pas encore éditable via un simple champ
`repoURL`, cf. axe 2 de l'initiative extensibilité) n'a pas été touché :
aucune Application déployée ne bascule sur gitlab.com par ce commit.

**Phase 4 (retrait SSO Dex↔GitLab)** faite le 2026-07-10 : décommissionné
plutôt que migré (cf. point 1 de la cartographie ci-dessus) — connector
Dex, mapping RBAC, provisioning OAuth au bootstrap, patch CA dex-server,
route Gateway dédiée, tous retirés. Login ArgoCD `admin` local seul
mécanisme d'accès restant (déjà le cas en pratique, `admin.enabled` jamais
désactivé).

**Phase 5 (runner autonome gitlab.com)** faite le 2026-07-10 : nouvelle
Application `gitlab-runner-com` (`platform-gitops`, chart officiel
`gitlab-runner` 0.88.2 — même version que le sous-chart du GitLab local,
cohérent avec l'image helper arm64 déjà pinnée), namespace dédié
`gitlab-runner`, en parallèle du runner local (rien retiré côté
`platform/gitlab/values-local.yaml`). Token créé par le nouveau
`platform-bootstrap/scripts/gitlab-runner-token-com.py`
(`runner_type: group_type`, scope groupe `k8s-gitops-lab`, via le PAT —
`instance_type` confirmé impossible sur gitlab.com, pas admin d'instance
SaaS). CA Zscaler montée via `certsSecretName` pour que le process
`gitlab-runner` joigne gitlab.com (même contournement que Grafana Alloy) ;
les pods de job restent couverts par `CUSTOM_CA_CERTS` côté
`ci-templates`, mécanisme déjà en place. **Validé en direct** : pod
`1/1 Running`, logs `Runner registered successfully` /
`Verifying runner... is valid`, runner confirmé `online` /
`job_execution_status: idle` via l'API gitlab.com (id `54241190`,
description `k3d-poc-devops-com`) — TLS et auth fonctionnent bout en
bout, aucune pipeline réelle basculée dessus pour l'instant.

**Phase 6 (cutover repoURL — premier consommateur réel basculé)** faite le
2026-07-10 : `helloworld` est la première app dont le déploiement GitOps
tourne réellement depuis gitlab.com. Deux corrections minimales requises
(`platform-bootstrap`) : `platform_inventory.py::_normalize_app` écrasait
`manifests.argocdRepoURL` sans condition — seul champ à ne pas suivre le
pattern « dérivé si absent » des autres, alors que le schéma JSON
autorisait déjà la surcharge (axe 1) ; corrigé pour la respecter.
`render-argocd-apps.py::repo_creds` générait toujours l'`ExternalSecret`
racine du GitLab local, quelle que soit l'URL cible — ne le génère plus
que si `argocdRepoURL` pointe encore vers l'instance in-cluster.
`argocd/apps/helloworld.yaml` surcharge désormais `manifests.
argocdRepoURL` vers gitlab.com ; `make argocd-apps-render` a régénéré les
manifests (repo-creds.yaml local supprimé, remplacé par le secret
`gitlabcom-helloworld-iac-repo` déjà en place depuis la Phase 3).

**Précaution prise avant bascule** : les 4 branches (`dev`/`rec`/`preprod`/
`main`) de `helloworld-iac` vérifiées identiques entre `gitlab` (local) et
`gitlabcom` — seul `main` avait été poussé en Phase 1, les 3 autres
poussées juste avant ce commit.

**Vérifié en direct sur le cluster après bascule** : `AppProject
helloworld.sourceRepos` = gitlab.com ; l'ancien `ExternalSecret`/`Secret`
`gitlab-helloworld-iac-repo` prune proprement ; les 4 Applications
(`helloworld-{dev,rec,preprod,prod}`) re-ciblées sur gitlab.com,
`Synced`/`Healthy`, chacune sur le même SHA que la branche locale
correspondante (aucune divergence de contenu) ; pods applicatifs non
redémarrés (`restarts=0`, âge antérieur au cutover) — bascule
transparente, zéro interruption.

**Dette résiduelle Phase 4** : le pod `argocd-dex-server` live portait
encore le patch impératif de la Phase 4 initiale — **devenu sans objet** :
tout le namespace `gitlab` a été supprimé en Phase 7, `argocd-dex-server`
n'existe plus. Rien à nettoyer.

**Point d'attention opérationnel (clos par la Phase 7)** : le poste de
développement avait un problème d'accès TLS récurrent au GitLab local
(`gitlab.192.168.33.100.nip.io`), qui a empêché plusieurs push vers le
remote `gitlab` de `platform-gitops` pendant cette session. Sans objet
depuis la bascule big bang : le remote `gitlab` pointe désormais vers
gitlab.com (TLS public, aucun contournement requis).

---

## Bascule big bang (remplacement complet, pas de progressivité)

> Décidé le 2026-07-10, en cours de session, en rupture avec le
> séquencement progressif prévu plus haut (Phases 1 à 6) : l'opérateur a
> explicitement demandé un remplacement brutal du GitLab local par
> gitlab.com, **sans se soucier de la rupture de service**. Les phases
> précédentes (structure, Terraform, repo-creds, retrait SSO, runner,
> premier cutover) restent la base technique ; cette section documente ce
> qui a été fait en plus pour aller jusqu'au remplacement complet.

**Fait le 2026-07-10** :

1. **CI/CD gitlab.com câblé** (`gitlab-projects-iac/terraform-gitlabcom`) :
   variables de groupe héritées par tous les sous-groupes —
   `GITLAB_PUSH_TOKEN`, `GHCR_TOKEN`, `CUSTOM_CA_CERTS`,
   `INTERNAL_GITLAB_HOST=gitlab.com`, `GITLAB_PUSH_SCHEME=https`,
   `GITLAB_PUSH_USERNAME=oauth2`, `CI_TEMPLATES_PROJECT_PATH=k8s-gitops-lab/
   shared-ci/ci-templates`. **Dette assumée** : `GITLAB_PUSH_TOKEN` réutilise
   le PAT propriétaire (`var.gitlab_token`) au lieu d'un bot scopé — un vrai
   `gitlab_user` est impossible sur gitlab.com (`POST /api/v4/users` → 403,
   admin d'instance requis) et `gitlab_group_access_token` refuse aussi
   (400, indisponible sur le tier Free) ; recoupe l'axe 7 déjà suivi
   (dette de sécurité générale, pas spécifique à cette migration).
2. **Remotes basculés** : dans les 4 repos GitLab-first, l'ancien remote
   `gitlab` (local) supprimé, `gitlabcom` renommé `gitlab` — `git push
   gitlab main` pointe maintenant vers gitlab.com partout, sans changement
   de commande pour l'opérateur. `cockpit/CLAUDE.md` mis à jour.
3. **GitLab local décommissionné** : Application ArgoCD `gitlab` (chart
   Helm), `gitlab-routes`, `gitlab-minio-patch`, CR Terraform local
   `gitlab-iac` supprimés du GitOps ; ArgoCD a prune la release ; le
   namespace `gitlab` a été supprimé explicitement (PVCs Postgres/MinIO/
   Gitaly/Redis inclus — **perte de données assumée** : issues, MR, wiki,
   historique CI de l'instance locale, rien de tout ça n'était mirroré).
4. **Bootstrap nettoyé** (`platform-bootstrap`) : `gitlab-tf-credentials.py`,
   `gitlab-runner-token.py` (local) et leur helper partagé
   `gitlab_bootstrap.py` supprimés — sans ce nettoyage, un futur `make
   bootstrap` aurait attendu indéfiniment un GitLab local inexistant
   (`wait_for_gitlab_ready`). Ne reste que `gitlab-runner-token-com`.
5. **Bug structurel découvert et corrigé en validant un vrai pipeline** :
   les chemins relatifs (`shared-ci/ci-templates`, `hello-groupe/
   helloworld-iac`) codés en dur dans `ci-templates` et `helloworld`
   supposaient des groupes GitLab **top-level** (vrai en local) — faux sur
   gitlab.com où `shared-ci`/`hello-groupe` sont des **sous-groupes** de
   `k8s-gitops-lab`. Résultat : `include: component:` échouait
   (`content not found`) et `.fetch-scripts`/`deploy.py` auraient poussé
   au mauvais endroit. Corrigé : préfixe `k8s-gitops-lab/` dans
   `helloworld/.gitlab-ci.yml`, nouvelle variable
   `CI_TEMPLATES_PROJECT_PATH` dans `ci-templates` (portable, comme
   `GITLAB_PUSH_SCHEME`/`USERNAME`). Distinct d'un second point bloquant :
   `include: component:` sur gitlab.com exige que le projet source soit
   publié au **CI/CD Catalog** (mutation GraphQL `catalogResourcesCreate`
   + une `Release` par tag) — absent en local, découvert empiriquement
   (les composants `to-be-continuous/*` officiels résolvaient, pas les
   nôtres, tant que non publiés). `ci-templates` publié au catalogue ;
   nouveau tag `v3.0.11` avec les deux correctifs.
   `.releaserc.json` de `helloworld` ne fige plus d'URL locale non plus
   (portable, lit `GITLAB_URL` désormais passé en variable de job par
   `promote/template.yml`).
6. **Validé bout en bout par un vrai push** (`helloworld`, commit
   `2c12dba` puis `4dda6f8` après le correctif runner ci-dessous) :
   pipeline gitlab.com, `docker-buildah-build` (les deux services),
   `docker-hadolint`, `docker-trivy`, `docker-sbom`, `deploy-dev` et
   `semantic-release` tous **success**, tous exécutés sur notre propre
   runner (`runner.is_shared: false`) ; commit de déploiement réel
   constaté sur la branche `dev` de `helloworld-iac` (gitlab.com) ;
   Application ArgoCD `helloworld-dev` re-synced, pods `aarch64`
   `1/1 Running`, endpoint `/health` répond `{"status":"ok"}` — chaîne
   GitOps (build → publish → commit manifests → sync ArgoCD → pod sain)
   validée de bout en bout, contenu de l'image inclus.

**🟢 Bug résolu — images buildées en amd64 au lieu d'arm64** : les pods
`helloworld-svc`/`helloworld-gui` déployés par le premier test
crash-loopaient avec `exec format error`. **Cause racine identifiée** (et
c'est l'utilisateur qui a posé la bonne question — « le runner k8s est-il
systématiquement utilisé ? ») : le job `docker-buildah-build` n'avait
tourné ni sur notre runner ni forcément sur un runner arm64 — l'API du
job confirmait `runner.is_shared: true`,
`runner.description: 3-blue.saas-linux-small-amd64.runners-manager.
gitlab.com` : gitlab.com avait dispatché vers un **runner SaaS partagé**
(amd64), pas vers `gitlab-runner-com`. Explication : aucun job n'a de
`tags:`, notre runner accepte les jobs non taggés (`run_untagged: true`,
comportement par défaut), et les runners partagés du groupe étaient
encore actifs (`shared_runners_enabled: true`) — gitlab.com a préféré le
partagé, disponible plus vite. **Corrigé** :
`gitlab_group.root.shared_runners_setting = "disabled_and_unoverridable"`
(`gitlab-projects-iac/terraform-gitlabcom`) force tous les jobs du groupe
sur notre runner self-hosted, sans exception possible par un sous-groupe.
**Revalidé par un nouveau push réel** (`helloworld` commit `4dda6f8`) :
tous les jobs confirmés `runner.is_shared: false`, pods redéployés
`aarch64` (`uname -m`), `1/1 Running`, endpoint `/health` répond
`{"status":"ok"}`. Effet de bord noté au passage : un re-déclenchement du
même commit ne suffit pas à faire réapparaître une image corrigée sur un
nœud qui l'a déjà en cache (`imagePullPolicy: IfNotPresent` + même tag) —
il faut un nouveau commit/tag pour forcer un vrai re-pull, pas juste
relancer le pipeline.

**Dette connue, désormais sans objet** : `docker-sbom` (scan de sécurité,
composant `to-be-continuous`) échouait avec `Permission denied` en
écrivant `/etc/ssl/certs/ca-certificates.crt` sur le premier run — a
tourné sans erreur une fois exécuté sur notre propre runner (même
correctif que ci-dessus), la cause était probablement liée au runner
partagé (image/permissions différentes) plutôt qu'à une vraie contrainte
persistante. Plus vu depuis, à surveiller quand même.

**Reste à faire** : `ci-templates` (composants eux-mêmes) et
`platform-gitops` ne sont pas des « consommateurs » au même sens
qu'une app applicative — rien à basculer côté déploiement pour eux au-delà
de ce qui est déjà fait (miroir de contenu). Le mécanisme de cutover
(`argocdRepoURL` + préfixe de groupe + `CI_TEMPLATES_PROJECT_PATH`) est
posé et réutilisable pour toute future app.

**Dette découverte, partiellement traitée** : `cockpit/scripts/
gitlab-git-creds.py` + cible Make `gitlab-git-credentials` (PAT root,
git-credential local) ciblent encore l'instance locale décommissionnée —
**plus grave que noté initialement** : cette étape fait partie de la
séquence automatique `make platform-up` (`scripts/bootstrap.py::STEPS`),
pas juste d'une cible manuelle optionnelle — `platform-up` échoue donc
aujourd'hui à cette étape (secret `gitlab-gitlab-initial-root-password`
introuvable, namespace supprimé). Probablement aussi des hypothèses
dans `scripts/platform-verify.py`. Pas encore corrigé (nécessite de
décider si un équivalent gitlab.com est utile ou si l'étape doit
disparaître). Repéré le 2026-07-10 en vérifiant la synchro GitHub/
gitlab.com. **Corrigé au passage** : `cockpit`'s `gitlab-terraform-
credentials` (cible manuelle, hors séquence automatique) appelait
`make -C platform-bootstrap gitlab-tf-credentials`, une cible supprimée
en Phase 7 — cible cockpit retirée.

**Dette ci-dessus corrigée le 2026-07-10** : équivalent gitlab.com construit
plutôt que suppression de l'étape. `platform.yml` (`platform.gitlab.url` /
`.group` remplacent `namespace`/`internalHost`), `scripts/platform_checks.py`
(`gitlab_api`/`gitlab_pat_status` prennent une URL de base au lieu d'un
`domain` suffixé `gitlab.`, checks applicatifs préfixés par le groupe racine
`k8s-gitops-lab`) et `scripts/gitlab-git-creds.py` (ne provisionne plus de
PAT root depuis un secret K8s local ; stocke dans `git-credential` le
`GITLAB_TOKEN` fourni par l'opérateur — même convention que
`gitlab-reset.py`/`platform-destroy`) ont été mis à jour en conséquence,
ainsi que `platform-verify.py`. Le check `gitlab-web` (sonde non
authentifiée `/users/sign_in`) a été retiré : gitlab.com renvoie 403 sur
cette route sans navigateur, et l'unique route qui répond de façon fiable
(`/api/v4/version`) exige de toute façon le même PAT que `gitlab-pat` —
la sonde était devenue redondante, pas remplaçable à l'identique. Le
Makefile a aussi perdu `gitlab-password` (appelait une cible
`platform-bootstrap` déjà supprimée en Phase 7, repéré au passage) et ne
transmet plus `GITLAB_NAMESPACE` à `platform-bootstrap` (paramètre déjà
mort côté cible receveuse). Vérifié en conditions réelles : `make
gitlab-git-credentials` et `make platform-verify` interrogent désormais
gitlab.com et réutilisent la credential déjà présente dans le
`git-credential` de l'opérateur.

**State Terraform de `gitlab-iac-com` — backend Kubernetes conservé**
(décision du 2026-07-10) : essayé un backend HTTP GitLab-managed natif
(projet `infra/platform-gitops`, migration vérifiée « No drift », cf.
historique git) puis **revert** : l'opérateur veut un reset complet de
gitlab.com (groupe + sous-groupes + projets) avant chaque bootstrap de
la plateforme, pour des cycles de test reproductibles (cf. script
`gitlab-reset.py` ci-dessous) — stocker le state *dans* un projet
gitlab.com qui est lui-même supprimé par ce reset recrée la dépendance
circulaire (le state du tout premier apply qui recrée ce projet n'a
nulle part où vivre). Le backend Kubernetes n'a pas ce problème :
cluster et tofu-controller existent avant toute ressource gitlab.com.
Le secret `tfstate-default-gitlab-projects-iac-com` (jamais désynchronisé
pendant l'aller-retour, même `serial`/`lineage` vérifiés) reste la
source de vérité.

**Script de reset gitlab.com ajouté et intégré à `platform-destroy`**
(`cockpit/scripts/gitlab-reset.py`) : supprime définitivement
(`permanently_remove=true`) le groupe racine `k8s-gitops-lab` et tout son
contenu — sous-groupes, projets, issues, MR, pipelines. `make
platform-destroy` l'appelle désormais automatiquement après avoir détruit
les VMs (`--yes`, pas de prompt — cohérent avec le reste de cette cible
qui ne demande déjà aucune confirmation), à condition que `GITLAB_TOKEN`
soit exporté ; sinon l'étape est **sautée avec un avertissement clair**,
sans faire échouer la destruction des VMs (le token n'est pas censé
bloquer un teardown qui n'a par ailleurs rien à voir avec gitlab.com).
`make gitlab-reset` reste disponible seul (reset gitlab.com sans toucher
aux VMs). Résultat : `make platform-destroy` puis `make platform-up`
donne un cycle entièrement reproductible depuis zéro des deux côtés
(cluster ET gitlab.com), sans étape manuelle si `GITLAB_TOKEN` est déjà
dans l'environnement de l'opérateur.

**Révision du 2026-07-11 : le groupe racine n'est plus supprimé par le
reset.** Constaté en pratique lors d'un bootstrap : la création d'un
groupe top-level gitlab.com via l'API échoue systématiquement en `403
Forbidden` (sans détail), y compris sur un chemin jamais utilisé
auparavant — donc pas un conflit de chemin (la renomination immédiate du
groupe supprimé, supposée dans l'entrée ci-dessus, n'a pas pu être mise en
défaut mais n'est plus le sujet). Le compte a pourtant `can_create_group:
true` et un PAT avec le scope `api` complet ; il s'agit très probablement
de la vérification d'identité anti-abus que gitlab.com impose à la
création de nouveaux groupes top-level (l'API ne renvoie aucun détail,
contrairement à l'UI qui affiche l'étape de vérification). Le groupe
`k8s-gitops-lab` est donc désormais créé **une fois** manuellement via
l'UI, puis importé dans l'état Terraform (cf.
`gitlab-projects-iac/terraform-gitlabcom/main.tf`, commentaire sur
`gitlab_group.root`) — `gitlab-reset.py` ne le supprime plus jamais : il
vide seulement ses sous-groupes et projets directs (simple `DELETE`, pas
soumis à cette restriction, chemin libéré immédiatement). `make
gitlab-reset` / `make platform-destroy` gardent le même usage, juste un
comportement moins destructeur.

**Trou restant découvert le 2026-07-11 : le groupe racine survit aux resets
gitlab.com, mais pas aux rebuilds complets du cluster.** Le state Terraform
de `gitlab-iac-com` vit dans un Secret Kubernetes en-cluster, neuf à chaque
`make platform-destroy && make platform-up` (contrairement au groupe racine
sur gitlab.com, jamais supprimé). Résultat : le premier `terraform apply`
après un rebuild complet tente de recréer `gitlab_group.root` -> `403`,
bloquant toute la chaîne (sous-groupes/projets/variables gitlab.com jamais
créés, `git push gitlab` des 4 repos GitLab-first en échec). Corrigé :
nouvelle étape `scripts/gitlab-tf-state-seed.py` (`make gitlab-tf-state-seed`,
intégrée à la séquence `platform-up` juste après `platform-bootstrap`) —
réimporte `gitlab_group.root` dans le state en-cluster si absent (idempotent,
`platform_checks.check_gitlab_tf_state_seeded`), puis force un reconcile du
CR Terraform si celui-ci existe déjà. Au passage, `platform_checks.py` et
`scripts/gitlab-iac-wait.py` référençaient encore le CR Terraform `gitlab-iac`
(instance locale, décommissionnée) au lieu de `gitlab-iac-com` — corrigé,
c'était un trou distinct qui aurait fait tourner `make gitlab-projects-wait`
indéfiniment en cible sur un CR inexistant.

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
