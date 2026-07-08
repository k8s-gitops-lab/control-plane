# Fiches de tâches — extensibilité / généricité

> Descriptions auto-portantes des tâches restantes, à réaliser ultérieurement.
> Vue d'ensemble et statut : `backlog-extensibilite.md`. Checklist courte :
> `../TODO.txt`. Chaque tâche s'implémente **dans son repo propriétaire**,
> commit + push sur les deux remotes (`origin` puis `gitlab`). L'état actuel
> décrit ici a été vérifié sur le code le 2026-07-08 ; re-vérifier avant de
> commencer si les repos ont bougé.

Convention de chaque fiche : **Objectif**, **État actuel** (vérifié),
**Fichiers**, **Étapes**, **Critères d'acceptation**, **Vérification**,
**Pièges**.

---

## Axe 2 — Contrat de variables plateforme (dé-hardcoder domaine / registre)

**Objectif** — Un seul point de déclaration par couche pour le domaine
(`192.168.33.100.nip.io`) et le registre (`ghcr.io/k8s-gitops-lab`), propagé
par le canal natif de chaque couche. Instancier le produit ailleurs (autre
domaine/registre) sans grep multi-repo. Le contrat fixe les **noms** de
variables ; chaque repo garde son default local (cf. `AGENTS.md`).

**État actuel (vérifié le 2026-07-08, exploration approfondie)** — Le
domaine est en dur dans de nombreux fichiers de 9 repos. Une première passe
de vérification avait sous-estimé l'avancement réel ; ils se classent en 3
catégories :

1. **Sources de vérité déjà en place** (à garder, à documenter comme telles) :
   - `infra-iac/ansible/group_vars/all.yml` → `platform.domain` (socle cluster)
   - `platform-gitops/argocd/apps.yaml` → bloc `platform:` (`domain`, `registry.host`, `repoURL`, `targetRevision`) + `gitlab.internalHost`
   - `cockpit/platform.yml` → profil opérateur (surcharge)
   - `platform_constants()` (dans les deux copies de `platform_inventory.py`,
     voir ci-dessous) fusionne **déjà** `apps.yaml.platform` par-dessus
     `_PLATFORM_DEFAULTS` (`{**_PLATFORM_DEFAULTS, **inventory.get("platform", {})}`)
     — `apps.yaml` gagne déjà quand présent. Ce n'est pas une duplication
     active, juste un filet de sécurité / default de repli.
2. **Consommateurs à câbler sur une source** (le vrai travail) :
   - `platform-bootstrap/scripts/platform_inventory.py` **et**
     `toolbox/scripts/platform_inventory.py` — `_PLATFORM_DEFAULTS` (dict
     domaine+registre) et `platform_constants()` sont identiques entre les
     deux copies ; le reste du fichier diverge (toolbox a en plus
     `platform_repo_root()`/clone-to-tmp pour le mode MR, 210 lignes contre
     156). La dédup reste une dette réelle, mais plus fine qu'un simple
     fichier dupliqué à l'identique — seul le dict + la fonction de fusion
     le sont.
   - `gitlab-projects-iac/terraform/variables.tf` — `gitlab_url` a un
     default en dur, mais **n'est pas un consommateur mort** : `providers.tf`
     le consomme (`base_url = var.gitlab_url`), et la valeur réellement
     appliquée est fournie par le CR Flux
     `platform-gitops/argocd/platform/tf-controller/terraform-gitlab.yaml`
     (`spec.vars.gitlab_url`, en dur) — un 4ᵉ emplacement du domaine, non
     recensé initialement. C'est un manifest GitOps consommé tel quel par
     Flux → relève de la catégorie manifests (2b), pas d'un câblage
     applicatif simple (2a).
   - `ci-templates` — **n'a plus de `gitlab-ci.yml` monolithique** : le repo
     a été migré en composants CI/CD versionnés
     (`templates/{build-kaniko,deploy-gitops,promote}/template.yml`, voir
     axe 4, déjà fait). `registry_host` y est déjà un `spec:inputs` typé
     (default `ghcr.io`) dans `build-kaniko`. `INTERNAL_GITLAB_HOST` reste
     délibérément une `variables:` (pas un input) — décision documentée
     dans `ci-templates/AGENTS.md:38-40` ("constante de plateforme, pas un
     contrat par app"), à ne pas remettre en cause sans revisiter cette
     décision. **Le vrai trou confirmé** : `DOMAIN` est consommé par
     `templates/deploy-gitops/template.yml` (`environment.url`, dans les 4
     jobs `deploy-{dev,rec,preprod,prod}`) mais n'est déclaré **nulle part**
     côté GitLab CI réelle — seulement dans `.gitlab-ci-local.yml` (dev
     local uniquement). `ci-templates/scripts/deploy.py` lit bien `DOMAIN`
     en variable d'env (bon modèle), mais rien ne la fournit en pipeline
     réel aujourd'hui.
   - Variables CI de groupe GitLab : `gitlab_group_variable` dans
     `gitlab-projects-iac/terraform/main.tf` — **confirmé : aucune variable
     `DOMAIN`/`REGISTRY_HOST` n'existe**. C'est le canal natif manquant.
     Pattern déjà établi à suivre : `for_each = local.app_groups` (ex.
     `app_ghcr_token`, `app_zscaler_ca_b64`, `app_gitlab_push_token`,
     lignes 192-223) — les groupes d'app sont top-level et indépendants
     (pas d'héritage depuis le groupe `infra`), donc toute variable de
     plateforme doit être dupliquée par groupe selon ce même pattern.
   - Manifests plateforme (ingress/hostnames) : `platform-gitops/argocd/platform/{argocd-config/argocd-cm.yaml, argocd-ui/route.yaml, argocd-ui/dex-route.yaml, gitlab-routes/routes.yaml, gitlab/values-local.yaml, tf-controller/terraform-gitlab.yaml}`, `platform-bootstrap/argocd/dex-ca-patch.yaml`, `platform-bootstrap/ansible/roles/platform_bootstrap/defaults/main.yml`
   - Manifests d'app : `helloworld-iac/k8s/*route.yaml` (réécrits par `deploy.py update_routes` à chaque déploiement — donc pilotés par `DOMAIN`, à confirmer)
   - Scripts GitLab : `platform-bootstrap/scripts/{gitlab-dex-oauth-app,gitlab-runner-token,gitlab-tf-credentials}.py`, `cockpit/scripts/gitlab-git-creds.py`, `toolbox/scripts/{get-gitlab-token,platform_git}.py`
3. **Hors périmètre** (artefacts de dev local, ne pas toucher) :
   - `*/.gitlab-ci-local.yml`, `*/.claude/settings.local.json`

**Étapes** (par sous-phases, pour limiter le rayon) :
- **2a — Contrat + chemin applicatif** : prochain pas concret confirmé :
  créer une `gitlab_group_variable DOMAIN` (et éventuellement
  `REGISTRY_HOST`) par groupe d'app dans
  `gitlab-projects-iac/terraform/main.tf`, en suivant le pattern `for_each =
  local.app_groups` déjà en place (`app_ghcr_token` et consorts). C'est le
  canal natif manquant : `deploy-gitops/template.yml` (déjà en prod) attend
  `DOMAIN` en variable d'env mais rien ne la fournit en pipeline réel. Idem
  pour `_PLATFORM_DEFAULTS` : dédupliquer entre `platform-bootstrap` et
  `toolbox` (un seul exemplaire partagé, ou vendoring documenté avec check
  de divergence).
- **2b — Manifests plateforme** : paramétrer les hostnames d'ingress des
  composants (ArgoCD, GitLab, Dex) — plus lourd car ce sont des manifests
  GitOps statiques. Inclut aussi le câblage du CR Flux
  `tf-controller/terraform-gitlab.yaml` (`spec.vars.gitlab_url`, en dur
  aujourd'hui) sur `apps.yaml.platform.domain`. Option : overlay Kustomize
  avec un `configMapGenerator` / variable de substitution, ou values Helm là
  où c'est un chart. À traiter après 2a.

**Critères d'acceptation** — Changer le domaine se fait en éditant les
sources de vérité (`group_vars/all.yml` + `apps.yaml` + `platform.yml`) ; un
`grep -rl 192.168.33.100` hors sources de vérité et hors fichiers `.local`
ne retourne plus de **consommateur** applicatif. `make platform-verify`
(cockpit) passe toujours.

**Vérification** — `grep -rln '192.168.33.100'` avant/après (le compte des
consommateurs baisse) ; rendu inchangé côté ArgoCD (`render-argocd-apps.py
--check` dans `platform-bootstrap`) ; `terraform validate` dans `gitlab-projects-iac`.

**Pièges** — Ne pas casser les deux sources de vérité légitimes ; les
`_PLATFORM_DEFAULTS` sont un filet de sécurité, pas un doublon à supprimer
aveuglément (garder un default cohérent). Les manifests plateforme (2b) sont
consommés tels quels par ArgoCD : une substitution non résolue casse le
déploiement — tester sur un env jetable.

---

## Axe 4 — `ci-templates` → composants CI versionnés (`spec:inputs`) [FAIT]

**Objectif** — Remplacer le template monolithique étendu par variables libres
par des **CI/CD components** GitLab (`spec:inputs` typés, defaults, validation),
découpés en unités réutilisables. Une nouvelle capacité = un composant
versionné partagé, jamais du YAML local dans l'app.

**État actuel (vérifié le 2026-07-08)** — **Déjà implémenté**, non
documenté jusqu'ici. `ci-templates/gitlab-ci.yml` n'existe plus. Le repo
expose 3 composants versionnés (commit `9dbd58d feat: exposer les
pipelines comme components GitLab`) :
- `templates/build-kaniko/template.yml` — inputs `services` (regex),
  `registry_host` (default `ghcr.io`) ; jobs `build-dev`/`build-rec`.
- `templates/deploy-gitops/template.yml` — inputs `app_name`,
  `service_name`, `manifests_project_path`, `manifests_path` (default `k8s`),
  `has_preprod` (boolean, default `false`) ; jobs
  `deploy-{dev,rec,preprod,prod}` câblés en dur (reste pertinent pour
  l'axe 5). `INTERNAL_GITLAB_HOST`/`CI_SCRIPTS_DIR` restent des
  `variables:` par choix documenté (`ci-templates/AGENTS.md:38-40`), pas des
  inputs.
- `templates/promote/template.yml` — job `semantic-release`/`rollback-prod`.

`helloworld/.gitlab-ci.yml` consomme déjà les 3 via
`include: - component: $CI_SERVER_FQDN/shared-ci/ci-templates/<nom>@v2.0.0`
avec un bloc `inputs:` par composant, sans aucune logique inline — le
critère d'acceptation ci-dessous est satisfait. Versioning par tag
(`v2.0.0`), consommé par référence de projet + tag (pas besoin d'un
catalogue CI/CD formel `CI_CATALOG` — le mécanisme `include:component` par
chemin de projet fonctionne sans lui).

**Reste à faire (optionnel)** — Rien de bloquant. Pistes possibles si
utile : vérifier si un catalogue CI/CD formel apporterait un vrai bénéfice
(découverte, versions listées) vs le mécanisme actuel qui suffit déjà ;
généraliser `deploy-gitops` pour générer un job par environnement déclaré
au lieu de 4 jobs figés (voir axe 5, qui reste à faire).

**Critères d'acceptation** — ✅ Le `.gitlab-ci.yml` d'une app standard
n'assemble que des composants + inputs, aucune logique inline (vérifié sur
`helloworld`). Pipeline `helloworld` : à confirmer vert de bout en bout si
besoin de re-valider (pas re-testé dans cette passe documentaire).

**Vérification** — `glab ci lint` / lint API sur `helloworld` ; exécuter un
pipeline complet (`gitlab-ci-local` si dispo, cf. `.gitlab-ci-local.yml`) ;
comparer les images/tags produits avant/après.

**Pièges** — `.fetch-scripts` (clone du repo pour les scripts Python)
fonctionne déjà via `CI_SCRIPTS_DIR`. **Couplé à l'axe 5** : `deploy-gitops`
génère toujours 4 jobs figés (`deploy-{dev,rec,preprod,prod}`) + gate
`HAS_PREPROD` — le rendre déclaratif par environnement reste le travail de
l'axe 5, pas re-fait ici.

---

## Axe 5 — Séquence d'environnements déclarée par app

**Objectif** — Déclarer la séquence d'environnements par app (ex.
`environments: [dev, staging, prod]` en noms) et la consommer **des deux
côtés** : rendu ArgoCD ET génération des jobs de déploiement CI. `preprod`
cesse d'être un cas spécial.

**État actuel (vérifié)** —
- Côté rendu : `platform-bootstrap/scripts/platform_inventory.py:_normalize_app`
  accepte **déjà** un champ `environments:` en surcharge **complète** (chaque
  entrée = `name/branch/namespace/services[{name,url,ingressHost}]`), sinon
  dérive `dev → rec → (preprod si hasPreprod) → prod`. Le JSON Schema
  (`platform-gitops/argocd/apps.schema.json`, axe 1) modélise cette forme
  complète.
- Côté CI : `ci-templates/templates/deploy-gitops/template.yml` **câble en
  dur** `deploy-dev/rec/preprod/prod` avec une gate `HAS_PREPROD` (chemin mis
  à jour — le repo est désormais organisé en composants versionnés, voir
  axe 4, déjà fait). La séquence n'est donc PAS déclarative côté CI.
  `deploy.py` mappe `_ENV_BRANCH = {dev, rec, preprod, prod→main}` en dur.

**Étapes** —
- Étendre le schéma (axe 1) : autoriser `environments` en **liste de noms**
  (string) OU liste d'objets partiels `{name, branch?, promotion?}`, le reste
  dérivé. Garder la forme complète actuelle valide (rétro-compatible).
- Étendre `_normalize_app` pour dériver depuis une liste de noms (mapper
  `name → branch` : convention `prod→main`, sinon `name→name` ; `namespace`,
  `services.url/ingressHost` comme aujourd'hui).
- Généraliser `deploy.py._ENV_BRANCH` (le déduire de la séquence, pas une
  constante). Idem gates de promotion.
- Côté CI (couplé axe 4) : générer un job de deploy **par env déclaré**
  (composant paramétré par la liste), au lieu de 4 jobs figés + gate
  `HAS_PREPROD`.

**Critères d'acceptation** — Une app peut déclarer `environments: [dev,
prod]` (2 envs) ou `[dev, staging, preprod, prod]` (4 envs custom) et obtenir
le bon rendu ArgoCD **et** les bons jobs CI, sans toucher au template.
`helloworld` (dev/rec/preprod/prod) inchangé.

**Vérification** — `validate-inventory.py` accepte les nouvelles formes ;
`render-argocd-apps.py --check` cohérent ; pipeline d'une app à séquence
custom vert.

**Pièges** — Rétro-compatibilité de `helloworld.yaml` (`hasPreprod: true`
doit continuer à marcher, ou migrer explicitement vers `environments:`).
La branche `prod → main` est une convention à préserver. Le rendu ArgoCD et
la CI doivent lire **la même** définition d'ordre (source unique : l'entrée
d'inventaire).

---

## Axe 3 — Générateur natif ArgoCD (réduire `render-argocd-apps.py`) [spike]

**Objectif** — Consommer `argocd/apps/*.yaml` directement via un
`ApplicationSet` **git files generator** + `goTemplate`, pour supprimer ou
réduire l'étape de rendu (`render-argocd-apps.py`, 280 lignes) et son
répertoire `argocd/generated/`.

**État actuel (vérifié)** — Il existe déjà un `ApplicationSet` (généré, dans
`argocd/managed/apps-appset.yaml`) avec un git **directory** generator sur
`argocd/generated/apps/*`. Le rendu produit par app : `app-project.yaml`
(AppProject), `applicationset.yaml` (Applications par env), `namespaces.yaml`
(namespaces labellisés pour la distribution du secret `ghcr-pull`),
`repo-creds.yaml` (ExternalSecret du repo manifests), `kustomization.yaml`.
Le pipeline `platform-gitops/.gitlab-ci.yml` (`onboard-apps`) régénère et
committe au merge.

**Étapes (spike d'abord)** —
- Prototyper un `ApplicationSet` git **files** generator sur
  `argocd/apps/*.yaml` avec `goTemplate` : générer les Applications par env
  directement depuis les champs de l'entrée d'inventaire.
- Trancher explicitement ce qui **reste scripté** : les `Namespace`
  labellisés, les `ExternalSecret` de repo-creds, et les `AppProject` ne se
  génèrent pas trivialement via un seul ApplicationSet — évaluer un
  ApplicationSet séparé, un générateur de matrices, ou les garder en rendu.
- Documenter le verdict (natif vs scripté) avant d'implémenter.

**Critères d'acceptation** — Décision documentée + prototype fonctionnel sur
`helloworld` (Applications par env synchronisées Healthy) sans régression sur
namespaces/secrets/projet. Réduction nette de code custom si le spike est
concluant.

**Vérification** — Diff des `Application` ArgoCD générées avant/après ;
`argocd app list` Synced/Healthy ; les secrets `ghcr-pull` et repo-creds
toujours distribués.

**Pièges** — La dérivation par convention (`_normalize_app`) est riche
(services→images, hosts, argocdRepoURL in-cluster) : `goTemplate` doit
reproduire cette logique ou l'inventaire doit porter plus de champs. Risque
de déplacer la complexité plutôt que la supprimer — d'où le spike préalable.

---

## Axe 7 — Multi-tenancy GitLab : token de projet par app [sécurité]

**Objectif** — Remplacer le PAT personnel `root` partagé (scope `api`
complet, rayon d'explosion maximal — dette déjà documentée dans le PRD) par
un **project access token** scopé par couple `<app>`/`<app>-iac`.

**État actuel (vérifié)** — Le champ `group` (groupe GitLab dédié par app)
existe déjà dans l'inventaire ET dans `gitlab-projects-iac`
(`terraform/main.tf` : `app_projects`, `app_groups`, un `gitlab_group` par
app). Les pipelines applicatifs référencent `GITLAB_PUSH_TOKEN` (PAT root)
pour cloner `shared-ci/ci-templates` et pousser sur le dépôt manifests +
créer les tags (`semantic-release`). Note dans les commentaires TF : un
**project bot** issu d'un access token ne peut pas être ajouté à un autre
groupe/projet (limitation GitLab), ce qui contraint la conception cross-groupe.

**Étapes** —
- Créer un `gitlab_project_access_token` (ou group access token) par app dans
  `gitlab-projects-iac`, scopé au minimum (`write_repository` sur `<app>-iac`,
  lecture sur `ci-templates`).
- Distribuer le token à la CI de l'app via une `gitlab_project_variable` /
  `gitlab_group_variable` (masquée), en remplacement de `GITLAB_PUSH_TOKEN`
  partagé.
- Gérer l'expiration/rotation (les project access tokens expirent) :
  stratégie de renouvellement (Terraform `rotation` ou job planifié).
- Traiter la contrainte cross-groupe : l'accès en lecture à
  `shared-ci/ci-templates` depuis le token d'une app d'un autre groupe peut
  être refusé — évaluer un déploiement de `ci-templates` en public interne,
  ou un token dédié au clone.

**Critères d'acceptation** — Chaque app pousse ses manifests et crée ses
releases avec **son** token scopé ; le PAT root n'est plus référencé par les
pipelines applicatifs. Fuite d'un token = rayon limité à une app.

**Vérification** — Pipeline `helloworld` vert avec le token scopé ; tentative
d'accès hors périmètre refusée ; `terraform plan` idempotent.

**Pièges** — Sécurité-sensible : ne pas logguer les tokens (masquage CI) ;
l'expiration casse la CI silencieusement si non rotée ; la limitation
project-bot cross-groupe (documentée dans le TF) peut imposer un compromis de
conception. Coordonner avec l'axe 2 (les variables de groupe sont le canal de
distribution).

---

## Dette transverse relevée

- **Deux copies de `platform_inventory.py` partiellement dupliquées**
  (`platform-bootstrap/scripts/` et `toolbox/scripts/`) : seuls
  `_PLATFORM_DEFAULTS` et `platform_constants()` sont identiques entre les
  deux fichiers ; le reste diverge (`toolbox` a en plus
  `platform_repo_root()`/clone-to-tmp pour le mode MR — 210 lignes contre
  156). À dé-dupliquer au moins sur la partie identique (traiter avec l'axe
  2). Toute évolution du contrat de defaults doit aujourd'hui être faite
  deux fois.
- **`_normalize_app` vs `apps.schema.json`** : deux définitions du contrat
  susceptibles de diverger. Piste : générer/valider l'une depuis l'autre.
- **`DOMAIN` CI manquant (gap fonctionnel, pas juste dette cosmétique)** :
  `ci-templates/templates/deploy-gitops/template.yml` consomme `${DOMAIN}`
  dans `environment.url` (4 jobs) mais aucune `gitlab_group_variable DOMAIN`
  n'existe dans `gitlab-projects-iac` — seule `.gitlab-ci-local.yml` (dev
  local) la définit. À traiter en priorité dans l'axe 2a (voir étapes 2a).
- **`gitlab_url` : le default Terraform n'est jamais réellement appliqué**
  — `gitlab-projects-iac/terraform/variables.tf` déclare un default, mais la
  valeur effectivement utilisée par `providers.tf` est toujours celle
  fournie par le CR Flux `platform-gitops/argocd/platform/tf-controller/
  terraform-gitlab.yaml` (`spec.vars.gitlab_url`, en dur). C'est donc ce
  manifest qui est la vraie source de vérité de fait — à câbler sur
  `apps.yaml.platform.domain` en 2b.
- **Commits en attente vers `gitlab`** : remote injoignable le 2026-07-08,
  repousser quand accessible (`git push gitlab main` dans chaque repo touché).
