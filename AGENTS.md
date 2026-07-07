# AGENTS.md — control-plane

## Rôle du dépôt

`control-plane` orchestre tous les dépôts du POC. C'est le point d'entrée
unique pour provisionner l'environnement complet : cluster, plateforme et seed.
Il ne contient pas de code exécuté en production.

## platform.yml : profil de surcharge, pas source de vérité

`platform.yml` est un profil opérateur local : chemins des repos voisins et
valeurs effectivement passées aux Makefiles délégués (domaine, namespaces,
version ArgoCD). Chaque repo reste autonome avec ses propres defaults ; en
particulier, les versions du socle cluster (Kubernetes, Flannel, Helm,
charts...) sont pinnées dans `infrastructure/ansible/group_vars/all.yml`, pas
ici. Ne déclarer dans `platform.yml` que des valeurs réellement consommées
par une cible du Makefile. `scripts/export-env.py` le transforme en variables
shell exportées et mémorisées dans `.control-plane.env`.

## Commandes principales

```bash
make env               # Afficher les variables exportées (sans les appliquer)
make platform-up       # Tout provisionner depuis zéro (images Packer + cluster + bootstrap + git-creds + verify)
make platform-provision # Comme platform-up mais sans reconstruire les images Packer existantes
make platform-verify   # Smoke test de bout en bout (rejouable à tout moment)
make cluster-up        # Cluster seul (sans images Packer)
make platform-bootstrap # Bootstrap ArgoCD + plateforme seule
make platform-bootstrap START_AT=gitlab-tf-credentials # Reprendre à une étape
make gitlab-tf-credentials # Créer/rotater le PAT GitLab Terraform
make status            # État ArgoCD
```

## Ordre de préférence pour le déploiement

Quand plusieurs mécanismes sont possibles pour une même tâche de déploiement,
respecter cet ordre de préférence :

1. **Ressource Terraform ou Kubernetes déclarative** (provider TF, manifest
   appliqué par ArgoCD/Flux) — pas de script custom si la ressource native
   suffit.
2. **Ansible** (playbook/rôle) pour les tâches impératives multi-étapes
   (provisioning, orchestration, idempotence via modules) quand une ressource
   déclarative ne suffit pas.
3. **Make**, en dernier recours — cible manuelle simple qui enchaîne d'autres
   commandes ou expose un point d'entrée à l'opérateur, pas pour porter de la
   logique métier.

Exemple appliqué : les étapes de bootstrap ArgoCD/Flux (CA trust, install,
ingress, secret SOPS) vivent dans le rôle `platform_bootstrap` de
`platform-cicd/ansible/` ; le Makefile de `platform-cicd` ne fait qu'appeler
`ansible-playbook playbook-platform.yml --tags <étape>` dans ce même dépôt.

**Orchestration de plusieurs tâches** : quand il s'agit d'enchaîner plusieurs
étapes (séquence, reprise après échec, dépendances entre étapes), préférer
l'orchestration Ansible (playbook avec plusieurs tâches/rôles tagués,
`--start-at-task`, `--tags`) plutôt qu'un enchaînement de cibles Make. Make
reste pour exposer un point d'entrée unique à l'opérateur (ex. `make
bootstrap`), pas pour porter la logique de séquencement elle-même.

**Images Packer** : le code déployé dans les images Packer (`infrastructure/packer`)
doit passer par le `provisioner "ansible"` (réutilisant les rôles/playbooks
existants), jamais par un `provisioner "shell"` ad hoc — cf. `infrastructure/AGENTS.md`.

## Structure du code Ansible

Une tâche Ansible doit rester simple (une action/un module) et ne doit
**jamais lancer un autre run Ansible en sous-processus** — pas de tâche
`command`/`shell` qui invoque `ansible-playbook`, `ansible` ou
`ansible-galaxy`. Ce shell-out cassé la visibilité de l'exécution englobante
(`--check`/`--diff`, filtrage par tags, rapport idempotent) et duplique un
mécanisme qu'Ansible fournit déjà nativement.

Les mécanismes natifs de composition (`roles:`, `include_role`,
`import_role`, `include_tasks`) restent la bonne façon de réutiliser un
groupe de tâches — ce ne sont pas des tâches qui « exécutent d'autres
tâches » au sens shell, ce sont des directives de structuration déclarative
du même run Ansible.

## Workflow Git

Ne jamais modifier les fichiers directement dans GitLab. Toujours :
1. Modifier en local.
2. Committer localement.
3. Pousser vers les deux remotes : `git push origin main` puis `git push gitlab main`.

## Ce qu'il ne faut pas faire

- Ne pas modifier les dépôts voisins (`infrastructure`, `platform-cicd`, etc.)
  directement depuis ce dépôt — passer par leurs propres Makefiles.
- Ne pas hardcoder des valeurs de versions dans les Makefiles ; les lire depuis
  les variables exportées par `export-env.py`.
- Ne pas committer `.control-plane.env` (contient des chemins locaux absolus).
