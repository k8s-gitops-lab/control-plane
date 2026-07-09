# Carte des repos

Ce workspace est volontairement decoupe en plusieurs repos pour montrer les
frontieres d'une plateforme CI/CD GitOps. Pour apprendre le systeme, lire les
repos dans cet ordre.

| Repo | Role | A retenir |
|---|---|---|
| `cockpit` | Point d'entree operateur | Orchestre les autres repos sans devenir une dependance runtime. |
| `infra-iac` | Socle Kubernetes local | Cree les VMs, initialise Kubernetes et installe les add-ons reseau bas niveau. |
| `platform-bootstrap` | Bootstrap technique | Installe ArgoCD, configure le bootstrap initial et expose les commandes operateur. |
| `platform-gitops` | Etat GitOps suivi par ArgoCD | Contient `argocd/managed/`, `argocd/platform/` et l'inventaire applicatif. |
| `toolbox` | Outillage partage | Onboarding d'apps (PR sur l'inventaire), rendu des variables Terraform GitLab. |
| `gitlab-projects-iac` | Provisioning GitLab | Terraform (applique automatiquement par Flux) : cree/met a jour les projets GitLab, la protection de branches et les miroirs GitHub. |
| `ci-templates` | Pipeline applicatif generique | Template GitLab CI versionne, inclus par les apps. |
| `helloworld` | App exemple | Monorepo applicatif multi-services. |
| `helloworld-iac` | Manifests app exemple | Manifests Kubernetes promus par branches d'environnement. |

## Flux principal

1. `infra-iac` fournit le cluster Kubernetes local.
2. `platform-bootstrap` installe ArgoCD et applique le root Application.
3. ArgoCD lit `platform-gitops` et synchronise GitLab, les routes plateforme
   et les ApplicationSets applicatifs (les images applicatives sont poussées
   sur GHCR, pas sur un registry interne au cluster).
4. `toolbox` lit l'inventaire de `platform-gitops` et genere
   `apps.auto.tfvars.json` pour `gitlab-projects-iac` (les credentials ArgoCD
   des repos manifests sont fabriques en continu par External Secrets
   Operator).
5. Le Terraform de `gitlab-projects-iac` (applique automatiquement par Flux)
   cree ou met a jour les projets GitLab, la protection de branches et les
   miroirs GitHub.
6. `ci-templates` definit la chaine CI/CD consommee par `helloworld`, en
   s'appuyant sur les composants amont to-be-continuous (miroir local, voir
   ci-dessous).
7. `helloworld` pousse des images et modifie `helloworld-iac`.
8. ArgoCD deploie `helloworld-iac` dans les namespaces d'environnement.

## Diagramme de dependances

Convention : `A --> B` signifie "A depend de B" (A a besoin de B pour
fonctionner), comme un graphe de dependances npm/Maven — pas l'ordre
chronologique d'execution (voir le flux principal ci-dessus pour l'ordre).
Les fleches en pointilles marquent des dependances de deploiement/runtime
(ArgoCD, orchestration cockpit), les fleches pleines des dependances de
contenu (donnees, code, pipeline).

`platform-bootstrap` ne referencait plus recemment que le contenu de
`platform-gitops` via une valeur figee dans `argocd/root-app.yaml`
(`repoURL`). C'etait un couplage accidentel sans raison fonctionnelle :
`repoURL` est desormais une variable ansible (`gitops_repo_url`, template
`ansible.builtin.template`), donc cette arete a disparu du graphe.

Une dependance externe fait partie du graphe : le groupe GitLab local
`to-be-continuous` (projets `docker`, `semantic-release`...) est un **miroir**
de `gitlab.com/to-be-continuous`, cree et rafraichi par le Terraform de
`gitlab-projects-iac` (GitLab ne resout les `include:component` que sur sa
propre instance). `ci-templates` inclut ces composants amont a version figee
(`@6.1.0` pour docker) — c'est le seul point de mise a jour pour toutes les
apps. Ce miroir est critique pour tout build applicatif : sans lui, aucun
pipeline `build-docker` ne passe.

Il reste une paire de repos avec une dependance dans les deux sens :
`gitlab-projects-iac` <-> `platform-gitops`. Ce n'est pas une dette a
corriger : le trigger cote `platform-gitops`
(`argocd/platform/tf-controller/`) est un enchainement a 3 etages sequence
par sync-wave ArgoCD (secrets SOPS dechiffres, puis source Git, puis le CR
Terraform), et ce trigger ne depend jamais du pipeline GitLab CI de
`platform-gitops` (l'autre sens de l'arete) pour s'executer — ce dernier
n'est qu'une regeneration automatique de confort, pas un prealable. Le
bootstrap converge donc en un seul passage (`make platform-up` est
idempotent et auto-reparant) : ce n'est pas un deadlock, juste un graphe
statique qui affiche a la fois le chemin critique et une dependance de
confort entre les deux memes repos.

```mermaid
flowchart RL
    cockpit["cockpit\n(point d'entree, non-runtime)"]

    infra_iac["infra-iac"]
    platform_bootstrap["platform-bootstrap"]
    platform_gitops["platform-gitops"]
    toolbox["toolbox"]
    gitlab_projects_iac["gitlab-projects-iac"]
    ci_templates["ci-templates"]
    helloworld["helloworld"]
    helloworld_iac["helloworld-iac"]
    tbc["to-be-continuous\n(miroir GitLab local de gitlab.com/to-be-continuous)"]

    platform_bootstrap -->|"requiert un cluster K8s"| infra_iac
    platform_gitops -.->|"necessite ArgoCD installe"| platform_bootstrap
    toolbox -->|"lit l'inventaire de"| platform_gitops
    gitlab_projects_iac -.->|"chemin critique : CR tf-controller (sync-wave 1-3) de"| platform_gitops
    gitlab_projects_iac -->|"consomme apps.auto.tfvars.json de"| toolbox
    ci_templates -->|"projet GitLab cree/mirrore par"| gitlab_projects_iac
    helloworld -->|"projet GitLab cree/mirrore par"| gitlab_projects_iac
    helloworld_iac -->|"projet GitLab cree/mirrore par"| gitlab_projects_iac
    platform_gitops -.->|"confort : pipeline CI de regeneration heberge par"| gitlab_projects_iac
    tbc -->|"miroir cree/rafraichi par"| gitlab_projects_iac
    ci_templates -->|"include:component docker/semantic-release@version figee de"| tbc
    helloworld -->|"consomme le pipeline de"| ci_templates
    helloworld_iac -->|"manifests mis a jour par le pipeline de"| helloworld
    helloworld_iac -.->|"deploye par ArgoCD depuis"| platform_gitops

    cockpit -.->|"make -C ../infra-iac"| infra_iac
    cockpit -.->|"make -C ../platform-bootstrap"| platform_bootstrap
    cockpit -.->|"ghcr-token-init ecrit flux-secrets/"| platform_gitops
    cockpit -.->|"expose le chemin (hors bootstrap principal)"| toolbox
```
