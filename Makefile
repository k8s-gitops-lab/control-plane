SHELL := /bin/bash -e -o pipefail
.SHELLFLAGS := -e -o pipefail -c

CONFIG ?= platform.yml
ENV_FILE ?= .cockpit.env
MAKE_BIN ?= make
ENV = CONFIG="$(CONFIG)" python3 scripts/export-env.py > "$(ENV_FILE)" && . "$(ENV_FILE)"
START_AT ?=
STOP_AFTER ?=
SNAPSHOT_NAME ?= cluster-ready

.PHONY: help validate env vm-images-build vm-images-add vm-images cluster-up cluster-from-images snapshot-cluster restore-cluster platform-up platform-provision platform-from-snapshot platform-bootstrap platform-bootstrap-status platform-bootstrap-reset platform-down platform-destroy platform-verify argocd-password argocd-status ghcr-token-init ghcr-pull-secret-wait gitlab-reset gitlab-git-credentials gitlab-projects-wait argocd-apps-wait

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-24s\033[0m %s\n", $$1, $$2}'


validate: ## Verifie platform.yml, compile les scripts Python et valide les skills
	@python3 -m py_compile scripts/*.py && echo "OK: scripts Python"
	@CONFIG="$(CONFIG)" python3 scripts/export-env.py > /dev/null && echo "OK: platform.yml valide"
	@python3 scripts/validate-skills.py

env: ## Affiche les variables exportees depuis platform.yml
	@CONFIG="$(CONFIG)" python3 scripts/export-env.py

vm-images-build: ## Construit les boxes Vagrant k8s-master/k8s-worker via Packer
	@$(ENV); \
	echo "==> cockpit: vm-images-build -> make -C $$INFRASTRUCTURE_REPO/packer build"; \
	$(MAKE_BIN) -C "$$INFRASTRUCTURE_REPO/packer" build

vm-images-add: ## Ajoute les boxes Packer construites au registre Vagrant local
	@$(ENV); \
	echo "==> cockpit: vm-images-add -> vagrant box add"; \
	vagrant box add k8s-master "$$INFRASTRUCTURE_REPO/packer/output/k8s-master/package.box" --force; \
	vagrant box add k8s-worker "$$INFRASTRUCTURE_REPO/packer/output/k8s-worker/package.box" --force

vm-images: vm-images-build vm-images-add ## Construit et enregistre les images VM du cluster

cluster-up: ## Provisionne le socle cluster via ../infra-iac
	@$(ENV); \
	echo "==> cockpit: cluster-up -> make -C $$INFRASTRUCTURE_REPO up"; \
	$(MAKE_BIN) -C "$$INFRASTRUCTURE_REPO" up

cluster-from-images: vm-images-add ## Deploie le cluster depuis les boxes Packer k8s-master/k8s-worker
	@$(ENV); \
	echo "==> cockpit: cluster-from-images -> make -C $$INFRASTRUCTURE_REPO create-cluster"; \
	$(MAKE_BIN) -C "$$INFRASTRUCTURE_REPO" create-cluster

snapshot-cluster: ## Snapshot VirtualBox du cluster juste apres provisioning (avant platform-bootstrap)
	@$(ENV); \
	echo "==> cockpit: snapshot-cluster -> make -C $$INFRASTRUCTURE_REPO snapshot-cluster"; \
	$(MAKE_BIN) -C "$$INFRASTRUCTURE_REPO" snapshot-cluster SNAPSHOT_NAME="$(SNAPSHOT_NAME)"

restore-cluster: ## Restaure le cluster depuis un snapshot VirtualBox (SNAPSHOT_NAME, defaut cluster-ready)
	@$(ENV); \
	echo "==> cockpit: restore-cluster -> make -C $$INFRASTRUCTURE_REPO restore-cluster"; \
	$(MAKE_BIN) -C "$$INFRASTRUCTURE_REPO" restore-cluster SNAPSHOT_NAME="$(SNAPSHOT_NAME)"

platform-up: ## Sequence complete (images, cluster, snapshot, bootstrap, git-creds, verify), reprise automatique et re-verification des etapes deja faites
	python3 scripts/bootstrap.py --config "$(CONFIG)" --make "$(MAKE_BIN)"

platform-provision: ## Comme platform-up mais sans reconstruire les images VM
	python3 scripts/bootstrap.py --config "$(CONFIG)" --make "$(MAKE_BIN)" --from cluster-from-images

platform-from-snapshot: ## Restaure le snapshot VirtualBox (SNAPSHOT_NAME) puis rejoue platform-bootstrap -> verify
	@$(ENV); \
	echo "==> cockpit: platform-from-snapshot -> restore-cluster puis bootstrap --from platform-bootstrap"; \
	$(MAKE_BIN) -C "$$INFRASTRUCTURE_REPO" restore-cluster SNAPSHOT_NAME="$(SNAPSHOT_NAME)" && \
	python3 scripts/bootstrap.py --config "$(CONFIG)" --make "$(MAKE_BIN)" --from platform-bootstrap

platform-bootstrap-status: ## Affiche l'etat de reprise de platform-up (etapes terminees / restantes)
	python3 scripts/bootstrap.py --config "$(CONFIG)" --list

platform-bootstrap-reset: ## Efface l'etat de reprise sauvegarde de platform-up
	rm -f .bootstrap-state.json

platform-bootstrap: ## Bootstrap ArgoCD et la plateforme via ../platform-bootstrap, relancable avec START_AT=<etape>
	@$(ENV); \
	echo "==> cockpit: platform-bootstrap -> make -C $$PLATFORM_REPO_ROOT bootstrap"; \
	$(MAKE_BIN) -C "$$PLATFORM_REPO_ROOT" bootstrap \
	  ARGOCD_VERSION="$$ARGOCD_VERSION" \
	  GITLAB_DOMAIN="$$GITLAB_DOMAIN" \
	  ARGOCD_NAMESPACE="$$ARGOCD_NAMESPACE" \
	  START_AT="$(START_AT)" \
	  STOP_AFTER="$(STOP_AFTER)"

platform-verify: ## Smoke test de bout en bout : cluster, GitLab, ArgoCD Synced/Healthy, secret GHCR, PAT, projets et pipelines des apps
	@echo "==> cockpit: platform-verify -> scripts/platform-verify.py"; \
	CONFIG="$(CONFIG)" python3 scripts/platform-verify.py

gitlab-reset: ## ACTION DESTRUCTIVE : supprime le groupe gitlab.com k8s-gitops-lab (a lancer avant platform-up pour un bootstrap reproductible depuis zero). Necessite GITLAB_TOKEN.
	@echo "==> cockpit: gitlab-reset -> scripts/gitlab-reset.py"; \
	python3 scripts/gitlab-reset.py

gitlab-git-credentials: ## Verifie le PAT gitlab.com (GITLAB_TOKEN) stocke dans git-credential, le (re)stocke si absent/invalide/proche expiration
	@$(ENV); \
	echo "==> cockpit: gitlab-git-credentials -> scripts/gitlab-git-creds.py"; \
	GITLAB_URL="$$GITLAB_URL" \
	  python3 scripts/gitlab-git-creds.py

gitlab-projects-wait: ## Attend que le Terraform gitlab-iac (tf-controller) ait cree les projets GitLab applicatifs
	@echo "==> cockpit: gitlab-projects-wait -> scripts/gitlab-iac-wait.py"; \
	CONFIG="$(CONFIG)" python3 scripts/gitlab-iac-wait.py

argocd-apps-wait: ## Attend que toutes les Applications ArgoCD soient Synced/Healthy (convergence apres creation des projets GitLab)
	@echo "==> cockpit: argocd-apps-wait -> scripts/argocd-apps-wait.py"; \
	CONFIG="$(CONFIG)" python3 scripts/argocd-apps-wait.py

platform-down: ## Eteint les VMs de la plateforme sans les detruire
	@$(ENV); \
	echo "==> cockpit: platform-down -> make -C $$INFRASTRUCTURE_REPO down"; \
	$(MAKE_BIN) -C "$$INFRASTRUCTURE_REPO" down

platform-destroy: ## Detruit les VMs de la plateforme et reinitialise le groupe gitlab.com (GITLAB_TOKEN requis pour ce dernier volet)
	@$(ENV); \
	echo "==> cockpit: platform-destroy -> make -C $$INFRASTRUCTURE_REPO destroy"; \
	$(MAKE_BIN) -C "$$INFRASTRUCTURE_REPO" destroy
	@rm -f .bootstrap-state.json
	@if [ -n "$$GITLAB_TOKEN" ]; then \
	  echo "==> cockpit: platform-destroy -> scripts/gitlab-reset.py"; \
	  python3 scripts/gitlab-reset.py --yes; \
	else \
	  echo "==> cockpit: GITLAB_TOKEN absent, gitlab.com non reinitialise (lancer 'GITLAB_TOKEN=<pat> make gitlab-reset' a la main)"; \
	fi

argocd-password: ## Affiche le mot de passe admin initial d'ArgoCD
	@$(ENV); \
	echo "==> cockpit: argocd-password -> make -C $$PLATFORM_REPO_ROOT argocd-password"; \
	$(MAKE_BIN) -C "$$PLATFORM_REPO_ROOT" argocd-password \
	  ARGOCD_NAMESPACE="$$ARGOCD_NAMESPACE"

ghcr-token-init: ## Genere/chiffre platform-gitops/flux-secrets/ghcr-pull-secret.yaml a partir d'un compte + PAT GitHub (cle age locale creee si absente) ; committer/pousser platform-gitops ensuite
	CONFIG="$(CONFIG)" python3 scripts/ghcr-token-init.py

ghcr-pull-secret-wait: ## Attend que Flux depose le secret source GHCR (flux-secrets/, SOPS) dans argocd ; External Secrets le distribue ensuite aux namespaces applicatifs
	@echo "==> cockpit: ghcr-pull-secret-wait -> scripts/ghcr-pull-secret-wait.py"; \
	CONFIG="$(CONFIG)" python3 scripts/ghcr-pull-secret-wait.py

argocd-status: ## Affiche l'etat ArgoCD depuis ../platform-bootstrap
	@$(ENV); echo "==> cockpit: argocd-status -> make -C $$PLATFORM_REPO_ROOT status"; $(MAKE_BIN) -C "$$PLATFORM_REPO_ROOT" status ARGOCD_NAMESPACE="$$ARGOCD_NAMESPACE"
