# Production Constraints

This note lists constraints that would matter when moving this POC toward a
more realistic production setup.

## ArgoCD and GitOps

- Use one Kubernetes cluster per environment, especially for production.
- Register every target cluster in ArgoCD, or run a separate ArgoCD instance
  per environment.
- Use separate ArgoCD Projects for production and non-production workloads.
- Restrict production cluster access to ArgoCD by default.
- Restrict or disable manual sync for production applications.
- Define sync windows for freeze periods or controlled deployment windows.
- Require review before changing production manifests.
- Decide explicitly where self-heal is enabled, especially for risky resources.

## Security

- Use real TLS everywhere: GitLab, ArgoCD, gateways and application
  endpoints (GHCR, the external image registry, already enforces TLS).
- cert-manager is integrated (self-signed internal CA issuing the shared
  Gateway wildcard certificate). For production, swap the self-signed
  `ClusterIssuer` for a real ACME (Let's Encrypt) or enterprise PKI issuer.
- Use SSO/OIDC for ArgoCD and GitLab.
- Avoid shared admin/root users for normal operations.
- Enforce RBAC by team, application and environment.
- Use separate service accounts for CI, deployment and read-only operations.
- Store secrets with Vault, External Secrets Operator, Sealed Secrets or SOPS.
- Do not store raw production secrets in Git.
- Apply NetworkPolicies by default.
- Sign images and verify them with admission control.
- Use policy engines such as Kyverno or Gatekeeper for production guardrails.
- Avoid privileged runners unless isolated and explicitly justified.

## CI/CD

- Protect production branches and release tags.
- Restrict production deployment jobs to authorized maintainers or release
  managers.
- Use immutable image tags or image digests.
- Never deploy mutable tags such as `latest` to production.
- Build once and promote the exact same artifact across environments.
- Generate SBOMs.
- Gate production promotion on vulnerability scanning where required.
- Add dependency scanning and license policy checks.
- Keep rollback procedures tested, not only documented.
- Preserve an audit trail: approver, commit, image digest and deployment time.

## Infrastructure

- Use a highly available control plane for production clusters.
- Run multiple worker nodes across failure domains.
- Require resource requests and limits.
- Define PodDisruptionBudgets for critical workloads.
- Use HPA, KEDA or another scaling mechanism where relevant.
- Use cluster autoscaling when supported by the infrastructure.
- Use storage classes with clear backup and restore guarantees.
- Run ingress or Gateway infrastructure in HA mode.
- Manage DNS declaratively.

## Observability

- Centralize logs.
- Collect metrics with alerting, not only dashboards.
- Define SLIs and SLOs for user-facing services.
- Route alerts to the correct on-call ownership.
- Add synthetic checks for critical URLs.
- Alert on ArgoCD application health and sync failures.
- Alert on GitLab runner and pipeline failures.
- Retain audit logs for the required period.

## Reliability

- Test backup and restore for GitLab, ArgoCD and stateful workloads (GHCR
  retention/backup is GitHub's responsibility, not this platform's).
- Define disaster recovery targets: RPO and RTO.
- Define multi-zone or multi-region expectations when needed.
- Require readiness and liveness probes.
- Ensure graceful shutdown behavior.
- Perform capacity planning.
- Run load tests before production launch.
- Maintain runbooks for common incidents.

## Governance

- Clarify ownership for each environment and application.
- Define a change management process for production.
- Provide emergency break-glass access with audit.
- Retain compliance evidence where required.
- Pin versions for charts, images, CRDs and operators.
- Define upgrade strategy for Kubernetes, ArgoCD, GitLab, Traefik and Gateway
  API.

## Current POC Gaps

- TLS is issued by cert-manager but from a self-signed internal CA, not a
  publicly trusted certificate.
- Root/admin token usage is still central to the workflow.
- Branch protection is acceptable for a mono-operator POC but too weak for a
  real team.
- No external secret management.
- No image signing or admission policy.
- No high availability.
- No tested backup and restore story.
