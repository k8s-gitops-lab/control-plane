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
6. `ci-templates` definit la chaine CI/CD consommee par `helloworld`.
7. `helloworld` pousse des images et modifie `helloworld-iac`.
8. ArgoCD deploie `helloworld-iac` dans les namespaces d'environnement.

## Diagramme de dependances

Les numeros reprennent ceux du flux principal ci-dessus. Les fleches en
pointilles depuis `cockpit` ne sont pas des dependances d'execution : ce repo
orchestre les commandes des autres mais aucun d'eux n'a besoin de lui pour
fonctionner (cf. README).

```mermaid
flowchart LR
    cockpit["cockpit\n(point d'entree, non-runtime)"]

    infra_iac["infra-iac"]
    platform_bootstrap["platform-bootstrap"]
    platform_gitops["platform-gitops"]
    toolbox["toolbox"]
    gitlab_projects_iac["gitlab-projects-iac"]
    ci_templates["ci-templates"]
    helloworld["helloworld"]
    helloworld_iac["helloworld-iac"]

    infra_iac -->|"1. cluster K8s"| platform_bootstrap
    platform_bootstrap -->|"2. installe ArgoCD"| platform_gitops
    platform_gitops -->|"3. sync GitLab, routes, ApplicationSets"| gitlab_projects_iac
    toolbox -->|"4. lit l'inventaire"| platform_gitops
    toolbox -->|"4. genere apps.auto.tfvars.json"| gitlab_projects_iac
    gitlab_projects_iac -->|"5. cree/MAJ projets + miroirs GitHub"| ci_templates
    ci_templates -->|"6. pipeline CI/CD"| helloworld
    helloworld -->|"7. push image, modifie manifests"| helloworld_iac
    platform_gitops -.->|"8. ArgoCD deploie"| helloworld_iac

    cockpit -.orchestre.-> infra_iac
    cockpit -.orchestre.-> platform_bootstrap
    cockpit -.orchestre.-> platform_gitops
    cockpit -.orchestre.-> toolbox
```
