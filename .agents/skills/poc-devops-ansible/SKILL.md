---
name: poc-devops-ansible
description: 'Ansible conventions specific to the poc-devops workspace (control-plane, infrastructure, platform-cicd) -- when to use Ansible vs Terraform/Kubernetes vs Make, task structure rules, and the Packer build-time/runtime split. Use when writing or reviewing Ansible playbooks, roles, tasks, or Packer provisioners in this workspace.'
---

# Ansible poc-devops

Regles extraites de `control-plane/AGENTS.md` (@ f040e3e, 2026-07-07),
`infrastructure/AGENTS.md` (@ a17540b, 2026-07-04) et
`platform-cicd/AGENTS.md` (@ f756db5, 2026-07-04). Si ces fichiers ont
change depuis ces commits, re-verifier les faits ci-dessous avant de les
appliquer. Specifique a ce workspace ; pour des conseils Ansible
generiques, voir le skill `ansible-automation`.

## Carte des playbooks du workspace

| Repo | Playbook | Roles / contenu | Invoque par |
|---|---|---|---|
| `infrastructure` | `ansible/playbook.yml` | Provisioning des noeuds k8s (build-time + runtime) | Vagrant, Packer (`provisioner "ansible"`) |
| `infrastructure` | `ansible/playbook-cluster.yml` | Etapes cluster-dependantes | `make` de `infrastructure` |
| `platform-cicd` | `ansible/playbook-platform.yml` | `platform_bootstrap`, `argocd_trust_ca` | `make bootstrap` de `platform-cicd` |

Toujours prefixer un chemin de playbook par son repo : deux playbooks
peuvent porter le meme nom dans des repos differents.

## Ordre de preference pour le deploiement

Face a plusieurs mecanismes possibles pour une meme tache, respecter cet
ordre :

1. **Ressource declarative Terraform ou Kubernetes** (provider TF, manifest
   applique par ArgoCD/Flux) — pas de script ou de role custom si la
   ressource native suffit.
2. **Ansible** (playbook/role) pour les taches imperatives multi-etapes
   (provisioning, orchestration, idempotence via modules) quand une
   ressource declarative ne suffit pas.
3. **Make**, en dernier recours — cible manuelle simple qui enchaine
   d'autres commandes ou expose un point d'entree a l'operateur, jamais pour
   porter de la logique metier.

Exemple applique (`platform-cicd`) : les etapes de bootstrap
ArgoCD/Flux/GitLab (CA trust, install, ingress, secret SOPS) vivent dans le
role `platform_bootstrap` invoque par `ansible/playbook-platform.yml` ; le
Makefile ne fait qu'appeler
`ansible-playbook playbook-platform.yml --tags <etape>`.

## Orchestration multi-etapes : Ansible, pas Make

Des qu'il s'agit d'enchainer plusieurs etapes (sequence, reprise apres
echec, dependances entre etapes), l'orchestration va dans un playbook
Ansible (roles/taches taguees, `--start-at-task`, `--tags`), pas dans un
enchainement de cibles Make qui s'appellent l'une l'autre. Make reste pour
exposer un point d'entree unique a l'operateur, pas pour porter le
sequencement lui-meme. Points d'entree reels :

- `platform-cicd` : `make bootstrap` (relancable avec `START_AT=<etape>`),
  `make bootstrap-from-<etape>`.
- `control-plane` : `make platform-bootstrap` (delegue a `platform-cicd`,
  accepte aussi `START_AT=<etape>`).

## Structure d'une tache Ansible

- **Une tache = une action/un module.** Ne jamais lancer un autre run
  Ansible en sous-processus : pas de tache `command`/`shell` qui invoque
  `ansible-playbook`, `ansible` ou `ansible-galaxy`. Ce shell-out casse la
  visibilite de l'execution englobante (`--check`/`--diff`, filtrage par
  tags, rapport idempotent) et duplique un mecanisme qu'Ansible fournit deja
  nativement.
- **Composition native uniquement** : `roles:`, `include_role`,
  `import_role`, `include_tasks` pour reutiliser un groupe de taches. Ce ne
  sont pas des taches qui « executent d'autres taches » au sens shell, ce
  sont des directives de structuration declarative du meme run Ansible.

## Images Packer : provisioner ansible, jamais shell ad hoc

Le code deploye dans les images Packer (`infrastructure/packer/*.pkr.hcl`)
doit passer par le `provisioner "ansible"`, en reutilisant les
roles/playbooks existants (`infrastructure/ansible/playbook.yml`, avec
`--skip-tags` pour exclure les etapes qui dependent d'un cluster actif) —
jamais par un `provisioner "shell"` ad hoc. Pour une nouvelle etape de
provisioning : ajouter un role/tag Ansible et l'inclure dans le playbook
existant, pas du shell inline dans le fichier Packer.

## Build-time (Packer) vs runtime (post-demarrage VM)

Deux phases distinctes, criteres de repartition :

**Phase 1 — Packer (image), une seule fois**
Taches independantes du cluster : pas d'API server, pas de token kubeadm,
pas de dependance a la topologie reseau (IPs/noms des autres noeuds), aucun
secret ou certificat propre a une instance specifique, idempotentes pour
toute VM issue de cette image. Exemples : containerd, kubelet/kubeadm/
kubectl, modules kernel, sysctl, CA corporate, binaire Helm, `swapoff -a`
permanent.

**Phase 2 — post-demarrage des VMs (cluster actif)**
Taches qui necessitent un cluster actif : produisent ou consomment un
certificat/token unique a cette instance, ou appellent `kubectl`/`helm`
contre l'API server. Exemples : `kubeadm init`, kubeconfig, CNI Flannel,
metrics-server, join-command, join worker, CRDs Gateway API,
local-path-provisioner, MetalLB/Traefik (`helm upgrade --install`), Gateway
partagee.

Si une tache remplit les criteres de la Phase 1 mais reste executee en
Phase 2, c'est une dette a signaler explicitement (cf. tableau "Opportunite
non encore exploitee" dans `infrastructure/README.md`) — ne pas la deplacer
silencieusement sans le documenter.

## A faire / A eviter

### A faire

- Verifier avant d'ecrire une tache : une ressource Terraform/Kubernetes
  declarative suffirait-elle deja ?
- Utiliser `--tags`/`--start-at-task` pour la reprise apres echec, pas un
  flag Make custom qui reimplemente le sequencement.
- Lister les tags reels avant d'en citer un dans une doc ou une cible Make :
  `ansible-playbook <playbook> --list-tags` — ne jamais recopier une liste
  de tags depuis une doc sans la verifier.
- Garder les tags Ansible coherents avec les cibles Make qui les exposent
  (`make bootstrap START_AT=<etape>` doit correspondre a un tag reel du
  playbook).

### A eviter

- `command`/`shell` qui invoque `ansible-playbook`, `ansible` ou
  `ansible-galaxy` en sous-processus.
- `provisioner "shell"` dans un fichier Packer pour une etape qui pourrait
  etre un role Ansible.
- Coder la sequence de plusieurs etapes dans le Makefile plutot que dans le
  playbook.
- Citer un chemin de playbook sans son repo (`ansible/playbook.yml` existe
  dans plusieurs repos).
