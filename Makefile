CONFIG ?= platform.yml
ENV = ./scripts/export-env.py > /tmp/control-plane.env && . /tmp/control-plane.env

.PHONY: help env cluster-up platform-bootstrap gitlab-seed argocd-repo-creds status

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-24s\033[0m %s\n", $$1, $$2}'

env: ## Affiche les variables exportees depuis platform.yml
	@./scripts/export-env.py

cluster-up: ## Provisionne le socle cluster via ../cluster
	@$(ENV); \
	$(MAKE) -C "$$CLUSTER_REPO" up \
	  gateway_api_version="$$GATEWAY_API_VERSION" \
	  metallb_chart_version="$$METALLB_CHART_VERSION" \
	  traefik_chart_version="$$TRAEFIK_CHART_VERSION"

platform-bootstrap: ## Bootstrap ArgoCD et la plateforme via ../platform-cicd
	@$(ENV); \
	$(MAKE) -C "$$PLATFORM_REPO_ROOT" bootstrap \
	  ARGOCD_VERSION="$$ARGOCD_VERSION" \
	  GITLAB_DOMAIN="$$GITLAB_DOMAIN" \
	  GITLAB_NAMESPACE="$$GITLAB_NAMESPACE" \
	  ARGOCD_NAMESPACE="$$ARGOCD_NAMESPACE" \
	  REGISTRY_NAMESPACE="$$REGISTRY_NAMESPACE"

gitlab-seed: ## Seed les projets GitLab via ../toolbox
	@$(ENV); \
	$(MAKE) -C "$$TOOLBOX_REPO" gitlab-seed \
	  PLATFORM_REPO_ROOT="$$PLATFORM_REPO_ROOT" \
	  GITLAB_DOMAIN="$$GITLAB_DOMAIN" \
	  GITLAB_NAMESPACE="$$GITLAB_NAMESPACE" \
	  CI_TEMPLATE_SOURCE_DIR="$$CI_TEMPLATE_SOURCE_DIR"

argocd-repo-creds: ## Cree les credentials ArgoCD pour les repos manifests prives
	@$(ENV); \
	$(MAKE) -C "$$TOOLBOX_REPO" argocd-repo-creds \
	  PLATFORM_REPO_ROOT="$$PLATFORM_REPO_ROOT" \
	  GITLAB_DOMAIN="$$GITLAB_DOMAIN" \
	  GITLAB_NAMESPACE="$$GITLAB_NAMESPACE" \
	  ARGOCD_NAMESPACE="$$ARGOCD_NAMESPACE"

status: ## Affiche l'etat ArgoCD depuis ../platform-cicd
	@$(ENV); $(MAKE) -C "$$PLATFORM_REPO_ROOT" status ARGOCD_NAMESPACE="$$ARGOCD_NAMESPACE"
