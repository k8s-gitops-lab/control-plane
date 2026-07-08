# Backlog — extensibilité / généricité du produit

> Initiative transverse décidée le 2026-07-08 : rendre le produit plus
> extensible et instanciable ailleurs (autre domaine, autre registre,
> plusieurs équipes). Ce fichier suit l'avancement ; chaque axe est
> implémenté **dans son repo propriétaire**, jamais depuis `cockpit`
> (cf. `AGENTS.md`). L'état actuel ci-dessous a été vérifié sur le code —
> plusieurs axes sont déjà partiellement en place. Les fiches de tâches
> détaillées (`docs/tasks-extensibilite.md`) et le pense-bête `TODO.txt` ont
> été supprimés le 2026-07-08 car redondants avec ce fichier ; les points
> clés (pièges, critères de vérification, dette transverse) ont été repliés
> dans les sections ci-dessous. Ce fichier est désormais l'unique support de
> suivi de l'initiative.

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
Le domaine `192.168.33.100.nip.io` reste en dur dans une vingtaine de
fichiers de 9 repos au total.

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

**État actuel (partiel)** : il existe déjà un `ApplicationSet` avec un git
*directory* generator sur `argocd/generated/apps/*`, mais ces répertoires
sont produits par une étape de rendu (`render-argocd-apps.py`, 280 lignes,
génère aussi namespaces, ExternalSecrets, AppProjects).

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

**État actuel (vérifié le 2026-07-08)** : déjà implémenté, non documenté
jusqu'ici. `ci-templates/gitlab-ci.yml` n'existe plus — le repo expose 3
composants versionnés (`templates/{build-kaniko,deploy-gitops,promote}/
template.yml`), chacun avec `spec:inputs` typés (defaults, regex).
`helloworld/.gitlab-ci.yml` consomme déjà `include:component@v2.0.0` avec
un bloc `inputs:` par composant, sans aucune logique inline.

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

## Dette transverse

- [ ] Repousser tous les commits en attente vers le remote `gitlab`
  (injoignable depuis l'environnement le 2026-07-08 ; commits déjà poussés
  sur `origin`, cf. règle GitHub-fait-foi du `CLAUDE.md`).

(Les autres points de dette relevés — dérivation de `_normalize_app` depuis
le JSON Schema, `gitlab_group_variable DOMAIN` manquante — sont déjà suivis
respectivement dans les sections Axe 1 et Axe 2 ci-dessus.)
