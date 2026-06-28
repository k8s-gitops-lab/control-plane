from __future__ import annotations

import sys
import os
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "platform.yml"


def shell_quote(value: object) -> str:
    text = str(value)
    return "'" + text.replace("'", "'\"'\"'") + "'"


def main() -> None:
    config_path = Path(os.environ.get("CONFIG", DEFAULT_CONFIG))
    if not config_path.is_absolute():
        config_path = ROOT / config_path

    with config_path.open() as f:
        data = yaml.safe_load(f) or {}

    platform = data["platform"]
    versions = data["versions"]
    repos = platform["repositories"]

    values = {
        "GITLAB_DOMAIN": platform["domain"],
        "GITLAB_NAMESPACE": platform["gitlab"]["namespace"],
        "INTERNAL_GITLAB_HOST": platform["gitlab"]["internalHost"],
        "ARGOCD_NAMESPACE": platform["argocd"]["namespace"],
        "REGISTRY_NAMESPACE": platform["registry"]["namespace"],
        "REGISTRY_HOST": platform["registry"]["host"],
        "ARGOCD_VERSION": versions["argocd"],
        "KUBERNETES_VERSION": versions["kubernetes"],
        "KUBERNETES_MINOR_VERSION": versions["kubernetesMinor"],
        "FLANNEL_VERSION": versions["flannel"],
        "METRICS_SERVER_VERSION": versions["metricsServer"],
        "HELM_VERSION": versions["helm"],
        "LOCAL_PATH_PROVISIONER_VERSION": versions["localPathProvisioner"],
        "TRAEFIK_CHART_VERSION": versions["traefikChart"],
        "METALLB_CHART_VERSION": versions["metallbChart"],
        "GATEWAY_API_VERSION": versions["gatewayApi"],
        "CI_TEMPLATE_REF": versions["ciTemplateRef"],
        "CLUSTER_REPO": repos["cluster"],
        "PLATFORM_REPO_ROOT": repos["platform"],
        "GITOPS_REPO_ROOT": repos["gitops"],
        "TOOLBOX_REPO": repos["toolbox"],
        "CI_TEMPLATE_SOURCE_DIR": repos["ciTemplates"],
    }

    for key, value in values.items():
        print(f"export {key}={shell_quote(value)}")


if __name__ == "__main__":
    try:
        main()
    except KeyError as exc:
        sys.exit(f"Missing platform.yml key: {exc}")
