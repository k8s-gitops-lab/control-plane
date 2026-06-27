#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "platform.yml"


def shell_quote(value: object) -> str:
    text = str(value)
    return "'" + text.replace("'", "'\"'\"'") + "'"


def main() -> None:
    with CONFIG.open() as f:
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
        "TRAEFIK_CHART_VERSION": versions["traefikChart"],
        "METALLB_CHART_VERSION": versions["metallbChart"],
        "GATEWAY_API_VERSION": versions["gatewayApi"],
        "CI_TEMPLATE_REF": versions["ciTemplateRef"],
        "CLUSTER_REPO": ROOT / repos["cluster"],
        "PLATFORM_REPO_ROOT": ROOT / repos["platform"],
        "TOOLBOX_REPO": ROOT / repos["toolbox"],
        "CI_TEMPLATE_SOURCE_DIR": ROOT / repos["ciTemplates"],
    }

    for key, value in values.items():
        print(f"export {key}={shell_quote(Path(value).resolve() if isinstance(value, Path) else value)}")


if __name__ == "__main__":
    try:
        main()
    except KeyError as exc:
        sys.exit(f"Missing platform.yml key: {exc}")
