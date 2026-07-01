SHELL := /bin/bash -e -o pipefail
.SHELLFLAGS := -e -o pipefail -c

CONFIG ?= platform.yml
ENV_FILE ?= .control-plane.env
MAKE_BIN ?= make
ENV = CONFIG="$(CONFIG)" python3 scripts/export-env.py > "$(ENV_FILE)" && . "$(ENV_FILE)"
START_AT ?=
STOP_AFTER ?=

.PHONY: help validate env vm-images-build vm-images-add vm-images cluster-up cluster-from-images platform-up platform-provision platform-bootstrap platform-bootstrap-from-% platform-bootstrap-status platform-bootstrap-reset platform-down platform-destroy gitlab-tf-credentials argocd-repo-creds argocd-password gitlab-password status ghcr-pull-secret gitlab-git-creds

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-24s\033[0m %s\n", $$1, $$2}'


validate: ## Verifie platform.yml et compile les scripts Python
	@python3 -m py_compile scripts/export-env.py && echo "OK: export-env.py"
	@CONFIG="$(CONFIG)" python3 scripts/export-env.py > /dev/null && echo "OK: platform.yml valide"

env: ## Affiche les variables exportees depuis platform.yml
	@CONFIG="$(CONFIG)" python3 scripts/export-env.py

vm-images-build: ## Construit les boxes Vagrant k8s-master/k8s-worker via Packer
	@$(ENV); \
	echo "==> control-plane: vm-images-build -> make -C $$CLUSTER_REPO/packer build"; \
	$(MAKE_BIN) -C "$$CLUSTER_REPO/packer" build

vm-images-add: ## Ajoute les boxes Packer construites au registre Vagrant local
	@$(ENV); \
	echo "==> control-plane: vm-images-add -> vagrant box add"; \
	vagrant box add k8s-master "$$CLUSTER_REPO/packer/output/k8s-master/package.box" --force; \
	vagrant box add k8s-worker "$$CLUSTER_REPO/packer/output/k8s-worker/package.box" --force

vm-images: vm-images-build vm-images-add ## Construit et enregistre les images VM du cluster

cluster-up: ## Provisionne le socle cluster via ../cluster
	@$(ENV); \
	echo "==> control-plane: cluster-up -> make -C $$CLUSTER_REPO up"; \
	$(MAKE_BIN) -C "$$CLUSTER_REPO" up \
	  gateway_api_version="$$GATEWAY_API_VERSION" \
	  metallb_chart_version="$$METALLB_CHART_VERSION" \
	  traefik_chart_version="$$TRAEFIK_CHART_VERSION"

cluster-from-images: vm-images-add ## Deploie le cluster depuis les boxes Packer k8s-master/k8s-worker
	@$(ENV); \
	echo "==> control-plane: cluster-from-images -> make -C $$CLUSTER_REPO create-cluster"; \
	$(MAKE_BIN) -C "$$CLUSTER_REPO" create-cluster \
	  gateway_api_version="$$GATEWAY_API_VERSION" \
	  metallb_chart_version="$$METALLB_CHART_VERSION" \
	  traefik_chart_version="$$TRAEFIK_CHART_VERSION"

platform-up: ## Sequence complete (images, cluster, bootstrap, git-creds), reprise automatique en cas d'echec
	python3 scripts/bootstrap.py --config "$(CONFIG)" --make "$(MAKE_BIN)"

platform-provision: ## Comme platform-up mais sans reconstruire les images VM
	python3 scripts/bootstrap.py --config "$(CONFIG)" --make "$(MAKE_BIN)" --from cluster-from-images

platform-bootstrap-status: ## Affiche l'etat de reprise de platform-up (etapes terminees / restantes)
	python3 scripts/bootstrap.py --config "$(CONFIG)" --list

platform-bootstrap-reset: ## Efface l'etat de reprise sauvegarde de platform-up
	rm -f .bootstrap-state.json

platform-bootstrap: ## Bootstrap ArgoCD et la plateforme via ../platform-cicd, relancable avec START_AT=<etape>
	@$(ENV); \
	echo "==> control-plane: platform-bootstrap -> make -C $$PLATFORM_REPO_ROOT bootstrap"; \
	$(MAKE_BIN) -C "$$PLATFORM_REPO_ROOT" bootstrap \
	  ARGOCD_VERSION="$$ARGOCD_VERSION" \
	  GITLAB_DOMAIN="$$GITLAB_DOMAIN" \
	  GITLAB_NAMESPACE="$$GITLAB_NAMESPACE" \
	  ARGOCD_NAMESPACE="$$ARGOCD_NAMESPACE" \
	  START_AT="$(START_AT)" \
	  STOP_AFTER="$(STOP_AFTER)"

platform-bootstrap-from-%: ## Reprend le bootstrap plateforme depuis une etape platform-cicd (reprise fine, cf. platform-up --platform-start-at)
	$(MAKE) platform-bootstrap START_AT=$*

gitlab-git-creds: ## Cree un PAT GitLab root et l'injecte dans git-credential pour l'URL interne cluster
	@$(ENV); \
	echo "==> control-plane: gitlab-git-creds -> scripts/gitlab-git-creds.py"; \
	GITLAB_URL="https://gitlab.$$GITLAB_DOMAIN" \
	  GITLAB_NAMESPACE="$$GITLAB_NAMESPACE" \
	  INTERNAL_GITLAB_HOST="$$INTERNAL_GITLAB_HOST" \
	  python3 scripts/gitlab-git-creds.py

platform-down: ## Eteint les VMs de la plateforme sans les detruire
	@$(ENV); \
	echo "==> control-plane: platform-down -> make -C $$CLUSTER_REPO down"; \
	$(MAKE_BIN) -C "$$CLUSTER_REPO" down

platform-destroy: ## Detruit les VMs de la plateforme
	@$(ENV); \
	echo "==> control-plane: platform-destroy -> make -C $$CLUSTER_REPO destroy"; \
	$(MAKE_BIN) -C "$$CLUSTER_REPO" destroy
	@rm -f .bootstrap-state.json

gitlab-tf-credentials: ## Cree/rotate le PAT GitLab consomme par Terraform
	@$(ENV); \
	echo "==> control-plane: gitlab-tf-credentials -> make -C $$PLATFORM_REPO_ROOT gitlab-tf-credentials"; \
	$(MAKE_BIN) -C "$$PLATFORM_REPO_ROOT" gitlab-tf-credentials \
	  GITLAB_DOMAIN="$$GITLAB_DOMAIN" \
	  GITLAB_NAMESPACE="$$GITLAB_NAMESPACE"

argocd-repo-creds: ## Cree les credentials ArgoCD pour les repos manifests prives
	@$(ENV); \
	echo "==> control-plane: argocd-repo-creds -> make -C $$TOOLBOX_REPO argocd-repo-creds"; \
	$(MAKE_BIN) -C "$$TOOLBOX_REPO" argocd-repo-creds \
	  PLATFORM_REPO_ROOT="$$GITOPS_REPO_ROOT" \
	  GITLAB_DOMAIN="$$GITLAB_DOMAIN" \
	  GITLAB_NAMESPACE="$$GITLAB_NAMESPACE" \
	  ARGOCD_NAMESPACE="$$ARGOCD_NAMESPACE"

argocd-password: ## Affiche le mot de passe admin initial d'ArgoCD
	@$(ENV); \
	echo "==> control-plane: argocd-password -> make -C $$PLATFORM_REPO_ROOT argocd-password"; \
	$(MAKE_BIN) -C "$$PLATFORM_REPO_ROOT" argocd-password \
	  ARGOCD_NAMESPACE="$$ARGOCD_NAMESPACE"

gitlab-password: ## Affiche le mot de passe root initial de GitLab
	@$(ENV); \
	echo "==> control-plane: gitlab-password -> make -C $$PLATFORM_REPO_ROOT gitlab-password"; \
	$(MAKE_BIN) -C "$$PLATFORM_REPO_ROOT" gitlab-password \
	  GITLAB_NAMESPACE="$$GITLAB_NAMESPACE"

ghcr-pull-secret: ## Deploie secrets/ghcr-pull-secret.yaml (SOPS) comme secret source dans argocd ; chaque app le recopie dans ses namespaces via sa conf ArgoCD (Jobs generes par render-argocd-apps.py)
	@$(ENV); \
	echo "==> control-plane: ghcr-pull-secret dans $$ARGOCD_NAMESPACE"; \
	SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt \
	  sops --decrypt secrets/ghcr-pull-secret.yaml \
	  | kubectl apply -n "$$ARGOCD_NAMESPACE" -f -

status: ## Affiche l'etat ArgoCD depuis ../platform-cicd
	@$(ENV); echo "==> control-plane: status -> make -C $$PLATFORM_REPO_ROOT status"; $(MAKE_BIN) -C "$$PLATFORM_REPO_ROOT" status ARGOCD_NAMESPACE="$$ARGOCD_NAMESPACE"
