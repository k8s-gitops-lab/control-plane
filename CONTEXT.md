# POC DevOps — Control Plane

Vocabulaire du POC de chaîne CI/CD GitOps auto-hébergée (voir `docs/prd.md` pour la vision produit et `docs/repo-map.md` pour la répartition entre dépôts).

## Language

**App standard**:
Une app qui suit le pattern à deux dépôts (`<app>` pour le code, `<app>-iac` pour les manifests) et se déclare via une seule entrée d'inventaire `argocd/apps/<app>.yaml`, sans manifeste Kubernetes personnalisé hors du template `ApplicationSet`. C'est la seule catégorie couverte par le critère d'acceptation "aucune création manuelle" du PRD.
_Avoid_: App classique, app normale

**Seed/rendu**:
Deux étapes distinctes toujours enchaînées pour intégrer une nouvelle app : le seed GitLab (création/mise à jour des projets, protection de branches et miroirs GitHub, porté par le Terraform de `gitlab-projects-iac` — appliqué automatiquement par Flux à partir des variables générées par `toolbox`) et le rendu ArgoCD (génération de l'`ApplicationSet`/des manifests à partir de l'inventaire, porté par `platform-cicd`, ex. `render-argocd-apps.py`). Le PRD les nomme comme une seule "commande" par simplification narrative ; en pratique ce sont plusieurs commandes orchestrées ensemble (typiquement via une cible `make` côté `control-plane`).
_Avoid_: Commande de seed, script d'intégration

**Chemin de promotion uniforme**:
Toutes les apps suivent la même séquence ordonnée d'environnements disponibles (`dev` → `rec` → `preprod` optionnel → `prod`), chacune gardée par la même politique de gate de promotion — pas une garantie que toutes les apps traversent identiquement les mêmes environnements. `preprod` est un champ déclaratif de l'entrée d'inventaire `argocd/apps/<app>.yaml`, décidé par app, pas un choix global au niveau du POC.
_Avoid_: Pipeline de promotion, workflow de release

**Gate de promotion**:
Le contrôle applicatif qui autorise le passage d'un environnement à l'autre dans le chemin de promotion. Aujourd'hui un déclenchement manuel, identique pour toutes les apps ; devenir automatisable ou configurable par app est une direction future, pas encore décidée. Distinct de la protection de branche.
_Avoid_: Gate (seul), contrôle de déploiement

**Protection de branche**:
Le contrôle Git (GitLab) qui détermine qui peut pousser sur quelle branche d'environnement du dépôt manifests. Distinct de la gate de promotion.
_Avoid_: Gate (seul), branch protection

**Variable propre**:
Une valeur qu'une app passe au template CI versionné (`ci-templates`) pour le paramétrer — nom d'image, chemin de manifests, activation de `preprod`, etc. Toute nouvelle *capacité* (nouvelle étape, nouvelle condition) que le template ne prévoit pas nativement n'est pas une variable propre : c'est une extension à ajouter au template lui-même, jamais écrite en local dans le `.gitlab-ci.yml` d'une app — sous peine de sortir du périmètre "app standard".
_Avoid_: Paramètre CI, override
