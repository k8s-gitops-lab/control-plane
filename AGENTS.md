# AGENTS.md — cockpit

## Rôle du dépôt

`cockpit` orchestre tous les dépôts du POC. C'est le point d'entrée
unique pour provisionner l'environnement complet : cluster, plateforme et seed.
Il ne contient pas de code exécuté en production.

## platform.yml : profil de surcharge, pas source de vérité

`platform.yml` est un profil opérateur local : chemins des repos voisins et
valeurs effectivement passées aux Makefiles délégués (domaine, namespaces,
version ArgoCD). Chaque repo reste autonome avec ses propres defaults ; en
particulier, les versions du socle cluster (Kubernetes, Flannel, Helm,
charts...) sont pinnées dans `infra-iac/ansible/group_vars/all.yml`, pas
ici. Ne déclarer dans `platform.yml` que des valeurs réellement consommées
par une cible du Makefile. `scripts/export-env.py` le transforme en variables
shell exportées et mémorisées dans `.cockpit.env`.

## Commandes principales

```bash
make env               # Afficher les variables exportées (sans les appliquer)
make platform-up       # Tout provisionner depuis zéro (images Packer + cluster + bootstrap + git-creds + verify)
make platform-provision # Comme platform-up mais sans reconstruire les images Packer existantes
make platform-verify   # Smoke test de bout en bout (rejouable à tout moment)
make cluster-up        # Cluster seul (sans images Packer)
make snapshot-cluster  # Snapshot VirtualBox du cluster (avant platform-bootstrap)
make restore-cluster   # Restaure le cluster depuis un snapshot VirtualBox
make platform-from-snapshot # Restaure le snapshot puis rejoue platform-bootstrap -> verify
make platform-bootstrap # Bootstrap ArgoCD + plateforme seule
make platform-bootstrap START_AT=gitlab-runner-token-com # Reprendre à une étape
make platform-destroy  # ACTION DESTRUCTIVE : détruit les VMs et réinitialise le groupe gitlab.com (GITLAB_TOKEN requis pour ce dernier volet, sinon juste averti et sauté)
make gitlab-reset      # ACTION DESTRUCTIVE : reset seul du groupe gitlab.com (sans toucher aux VMs), même prérequis
make argocd-status     # État ArgoCD
```

## Gouvernance du développement

Le développeur de plateforme garde la maîtrise sur trois axes ; tout
développement (humain ou agent) doit s'y conformer :

1. **Maîtrise du produit** — ce qui est développé respecte la définition du
   produit ([`docs/prd.md`](docs/prd.md)) et est tracé dans le backlog
   ([`docs/backlog.md`](docs/backlog.md)). Pas de développement opportuniste
   hors périmètre : une **idée produit** passe par une entrée au backlog
   *avant* d'être implémentée ; un **correctif** ou une tâche d'entretien se
   trace au backlog au plus tard au moment du commit.
2. **Maîtrise du code** — le code produit reste simple, fiable et pas trop
   complexe : préférer la solution la plus simple qui fonctionne, éviter
   l'abstraction prématurée, et ne pas ajouter de mécanisme (option, couche,
   généricité) sans besoin avéré. Une évolution est considérée fiable quand
   `make validate` et `make platform-verify` passent.
3. **Maîtrise de l'architecture** — les dépendances entre repos restent
   celles décrites dans [`docs/repo-map.md`](docs/repo-map.md) (toute
   nouvelle dépendance inter-repos se justifie et se documente là), et les
   composants utilisés restent **maintenus et supportés**, dans des versions
   raisonnablement récentes : pas de composant abandonné, et les montées de
   version font partie de l'entretien normal de la plateforme (suivies dans
   la section « Entretien courant » du backlog).

Cette règle s'applique depuis tous les repos du workspace (chaque
`AGENTS.md` y renvoie) et se vérifie par une **revue de gouvernance
périodique** (trimestrielle, suivie au backlog) : PRD vs réalité, complexité
du code, carte des dépendances et fraîcheur des composants.

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
`platform-bootstrap/ansible/` ; le Makefile de `platform-bootstrap` ne fait qu'appeler
`ansible-playbook playbook-platform.yml --tags <étape>` dans ce même dépôt.

**Orchestration de plusieurs tâches** : quand il s'agit d'enchaîner plusieurs
étapes (séquence, reprise après échec, dépendances entre étapes), préférer
l'orchestration Ansible (playbook avec plusieurs tâches/rôles tagués,
`--start-at-task`, `--tags`) plutôt qu'un enchaînement de cibles Make. Make
reste pour exposer un point d'entrée unique à l'opérateur (ex. `make
bootstrap`), pas pour porter la logique de séquencement elle-même.

**Images Packer** : le code déployé dans les images Packer (`infra-iac/packer`)
doit passer par le `provisioner "ansible"` (réutilisant les rôles/playbooks
existants), jamais par un `provisioner "shell"` ad hoc — cf. `infra-iac/AGENTS.md`.

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

- Ne pas modifier les dépôts voisins (`infra-iac`, `platform-bootstrap`, etc.)
  directement depuis ce dépôt — passer par leurs propres Makefiles.
- Ne pas hardcoder des valeurs de versions dans les Makefiles ; les lire depuis
  les variables exportées par `export-env.py`.
- Ne pas committer `.cockpit.env` (contient des chemins locaux absolus).

## Documentation

Pas d'OpenWiki dans ce dépôt. Entrées réelles : `README.md` (parcours
utilisateurs, usage), `docs/repo-map.md` (rôle de chaque dépôt du workspace),
`docs/backlog.md` (backlog produit et décisions).
