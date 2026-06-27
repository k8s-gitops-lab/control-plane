CONFIG ?= platform.yml
ENV_FILE ?= .control-plane.env
MAKE_BIN ?= make
ENV = CONFIG="$(CONFIG)" python3 scripts/export-env.py > "$(ENV_FILE)" && . "$(ENV_FILE)"

.PHONY: help env vm-images-build vm-images-add vm-images cluster-up cluster-from-images platform-up platform-bootstrap gitlab-seed argocd-repo-creds status

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-24s\033[0m %s\n", $$1, $$2}'

env: ## Affiche les variables exportees depuis platform.yml
	@CONFIG="$(CONFIG)" python3 scripts/export-env.py

vm-images-build: ## Construit les boxes Vagrant k8s-master/k8s-worker via Packer
	@$(ENV); \
	$(MAKE_BIN) -C "$$CLUSTER_REPO/packer" build

vm-images-add: ## Ajoute les boxes Packer construites au registre Vagrant local
	@$(ENV); \
	vagrant box add k8s-master "$$CLUSTER_REPO/packer/output/k8s-master/package.box" --force; \
	vagrant box add k8s-worker "$$CLUSTER_REPO/packer/output/k8s-worker/package.box" --force

vm-images: vm-images-build vm-images-add ## Construit et enregistre les images VM du cluster

cluster-up: ## Provisionne le socle cluster via ../cluster
	@$(ENV); \
	$(MAKE_BIN) -C "$$CLUSTER_REPO" up \
	  gateway_api_version="$$GATEWAY_API_VERSION" \
	  metallb_chart_version="$$METALLB_CHART_VERSION" \
	  traefik_chart_version="$$TRAEFIK_CHART_VERSION"

cluster-from-images: vm-images-add ## Deploie le cluster depuis les boxes Packer k8s-master/k8s-worker
	@$(ENV); \
	$(MAKE_BIN) -C "$$CLUSTER_REPO" create-cluster \
	  gateway_api_version="$$GATEWAY_API_VERSION" \
	  metallb_chart_version="$$METALLB_CHART_VERSION" \
	  traefik_chart_version="$$TRAEFIK_CHART_VERSION"

platform-up: vm-images cluster-from-images platform-bootstrap ## Construit les images, deploie le cluster et bootstrappe la plateforme

platform-bootstrap: ## Bootstrap ArgoCD et la plateforme via ../platform-cicd
	@$(ENV); \
	$(MAKE_BIN) -C "$$PLATFORM_REPO_ROOT" bootstrap \
	  ARGOCD_VERSION="$$ARGOCD_VERSION" \
	  GITLAB_DOMAIN="$$GITLAB_DOMAIN" \
	  GITLAB_NAMESPACE="$$GITLAB_NAMESPACE" \
	  ARGOCD_NAMESPACE="$$ARGOCD_NAMESPACE" \
	  REGISTRY_NAMESPACE="$$REGISTRY_NAMESPACE"

gitlab-seed: ## Seed les projets GitLab via ../toolbox
	@$(ENV); \
	$(MAKE_BIN) -C "$$TOOLBOX_REPO" gitlab-seed \
	  PLATFORM_REPO_ROOT="$$PLATFORM_REPO_ROOT" \
	  GITLAB_DOMAIN="$$GITLAB_DOMAIN" \
	  GITLAB_NAMESPACE="$$GITLAB_NAMESPACE" \
	  CI_TEMPLATE_SOURCE_DIR="$$CI_TEMPLATE_SOURCE_DIR"

argocd-repo-creds: ## Cree les credentials ArgoCD pour les repos manifests prives
	@$(ENV); \
	$(MAKE_BIN) -C "$$TOOLBOX_REPO" argocd-repo-creds \
	  PLATFORM_REPO_ROOT="$$PLATFORM_REPO_ROOT" \
	  GITLAB_DOMAIN="$$GITLAB_DOMAIN" \
	  GITLAB_NAMESPACE="$$GITLAB_NAMESPACE" \
	  ARGOCD_NAMESPACE="$$ARGOCD_NAMESPACE"

status: ## Affiche l'etat ArgoCD depuis ../platform-cicd
	@$(ENV); $(MAKE_BIN) -C "$$PLATFORM_REPO_ROOT" status ARGOCD_NAMESPACE="$$ARGOCD_NAMESPACE"
