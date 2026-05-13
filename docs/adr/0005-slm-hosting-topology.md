# ADR-0005: SLM hosting topology on AWS

- Status: Accepted
- Date: 2026-05-09
- Deciders: Arun Veligatla (project author)
- Constitutional principle: XIII (SLM-First, Isolated, Swappable Model Boundary), with binding consequences for VI (Reproducible Local Dev and Deployment), VII (CI/CD Gates Merges), XI (Performance SLOs), and IX (Security)

## Context

ADR-0002 fixes the default model (Qwen2.5-7B-Instruct, bf16, ~14 GB of weights plus KV cache), the GPU runtime (vLLM v0.20.1), and the CPU-fallback runtime (llama.cpp b9090, GGUF Q4_K_M). The plan target cloud is AWS (per Spec Decision D2). The remaining decision is the AWS compute topology for the SLM workload, given that:

1. **ECS Fargate does not support GPUs.** The project's stateless application services (orchestration API, query API, ingest worker, validator, deployer, feedback worker) are well served by Fargate, but a GPU-bearing SLM cannot run there.
2. **Spec Principle XI binds** the diagnostic-event-to-policy-deployed latency to p95 ≤ 12 s; the SLM's contribution to that budget cannot exceed about 6 s under realistic load. That bound rules out instance families with insufficient memory bandwidth or instance counts that force long batch waits.
3. **Spec Principle VII model-cost discipline** binds the CI runner choices: full-profile load and 24-hour soak run on `workflow_dispatch` and on a nightly schedule, on a self-hosted GPU runner.
4. **Constitution Principle VI** requires reproducible local development; the same `PolicyGeneratorClient` interface must work locally and in cloud, with the CPU-fallback profile usable on a developer laptop.
5. **Spec Principle IX** requires SLM container isolation: the SLM workload must have no outbound network access except to the configured observability endpoints.

The choice is between (a) ECS-on-EC2 with a GPU instance family or (b) EKS with a GPU node group. Both can host the SLM workload; they differ on operational surface area, networking primitives, and scale-out ergonomics.

## Decision

**Default SLM hosting on AWS: ECS-on-EC2 with a Capacity Provider tied to an Auto Scaling Group of `g5.2xlarge` instances (forward-looking: `g6.xlarge`). Stateless application services on ECS Fargate. CPU-fallback SLM (llama.cpp + GGUF) on Fargate for environments without GPU access. EKS variant is preserved under `infra/terraform/eks/` behind a workspace flag for cluster-grade scaling.**

### Compute split (canonical)

| Workload | Default platform | Instance family | Reason |
|---|---|---|---|
| Stateless app services (orchestration API, query API, ingest worker, validator, deployer, feedback worker) | ECS Fargate | n/a | Lowest operational surface; Fargate sizing fits the per-service footprint; no GPU required. |
| SLM inference (vLLM, GPU profile, default) | ECS-on-EC2, Capacity Provider | `g5.2xlarge` (`A10G`, 24 GB) by default; `g6.xlarge` (`L4`, 24 GB) as the forward-looking equivalent | g5.xlarge's 24 GB GPU is already tight on bf16 weights plus KV cache once batch size grows; g5.2xlarge gives the headroom for sustained throughput. g4dn.xlarge (`T4`, 16 GB) is too tight on memory. |
| SLM inference (llama.cpp + GGUF, CPU fallback profile) | ECS Fargate | Fargate task with 4 vCPU and 16 GB memory | Behavior-equivalent under the same `PolicyGeneratorClient` contract; not SLO-conformant. Used for local quickstart in cloud-equivalent posture and for environments without GPU. |
| Stateful services (Postgres + TimescaleDB, Redis, Kafka) | RDS / ElastiCache / MSK | n/a | Per R-009, R-010, R-011. |

### Networking and isolation

- The SLM ECS service runs in a private subnet with **no internet egress route**. The security group denies all outbound traffic except to:
  - The OTel collector endpoint (ADOT sidecar or in-cluster collector).
  - The internal cluster DNS used by the orchestration services to reach the SLM service.
- The orchestration services reach the SLM via an internal Network Load Balancer (or service-discovery DNS) addressing the ECS-on-EC2 service on the `g5/g6` capacity provider.
- IAM task role on the SLM service grants only:
  - Read access to the S3 bucket holding the pinned weight cache (`s3:GetObject` on the manifest's prefix).
  - Read/write to the audit logs in CloudWatch Logs.
  - No KMS, no Secrets Manager, no other AWS APIs.

### Auto Scaling Group + Capacity Provider

- ASG is configured for `min=1`, `desired=1`, `max=4` with a target-tracking policy on the `slm_request_queue_depth` metric (custom CloudWatch metric emitted by the orchestration ingest worker).
- Capacity Provider strategy: `base=1`, `weight=100` for the GPU capacity provider; no Fargate fallback in the SLM service.
- Instance refresh on AMI update is gated to `workflow_dispatch` (matches the model-upgrade ADR cadence so weight rollouts and AMI rollouts are coordinated, never independent).
- Spot is **not** used for the SLM service in this ADR; spot interruptions during a long-running generation would breach SC-001 latency tail. Spot becomes a candidate when CollectMind ships its own retry-with-warm-handoff in a future feature.

### Storage and weight cache

- `infra/terraform/storage/` provisions an S3 bucket for the pinned model weights, server-side encryption (KMS), object-lock retention to match the SHA-pinning posture, and lifecycle rules that retain the rolling-90-day cache window per ADR-0002's rollback procedure.
- Containers pull weights at build time, not at runtime, so there is no S3 dependency on the hot path. Runtime uses the local layer; readiness probe verifies the SHA-256 manifest at start; mismatch fails closed.

### EKS variant (alternative; gated by Terraform workspace)

- `infra/terraform/eks/` defines a parallel topology: an EKS cluster with a managed GPU node group running on `g5.2xlarge` (or `g6.xlarge`), the same SLM container, the same security posture (no internet egress), the same ASG-equivalent Karpenter or managed-node-group autoscaling.
- Selecting EKS over ECS-on-EC2 is a per-environment Terraform workspace flag (`compute_platform = "ecs_ec2"` or `"eks"`).
- The contract tests for the `PolicyGeneratorClient` are unchanged across platforms; the deployment topology is the only thing that differs.

## Consequences

### Positive

- ECS-on-EC2 keeps the operational surface low: ECS' control plane is fully managed, no Kubernetes operators or RBAC story, no ingress controller selection, no separate cluster lifecycle. The team can ship the SLM container without standing up Kubernetes expertise as a precondition.
- The compute split keeps the stateless services on Fargate (no instance management) while keeping the GPU workload on the right-sized instance family. Costs scale with each tier independently.
- The CPU-fallback profile on Fargate gives a credible "cloud-equivalent local quickstart" path for environments where GPU is unavailable; it is not SLO-conformant but it is integration-test-conformant under Principle II.
- The EKS variant exists in code and is reviewable, so future scale-out (multi-tenant fleets, regional shards, GPU-pool consolidation across products) does not require an architectural rewrite.

### Negative

- ECS-on-EC2 carries instance-fleet management (AMI updates, OS patching). Mitigation: managed AMIs from the ECS team, automated weekly patch refresh on a `workflow_dispatch` trigger, instance refresh policy.
- `g5.2xlarge` is materially more expensive than CPU compute. Mitigation: ASG `min=1, max=4` keeps the steady-state cost bounded; full-profile load and soak run only on `workflow_dispatch` and nightly per Principle XIV.
- The cross-AZ networking pattern is more involved on ECS-on-EC2 than on Fargate: the ASG must span at least two AZs to satisfy the 99.9 percent availability SLO (SC-012), and Capacity Provider rebalancing must be tuned to avoid mid-generation interruption. Tuning is recorded in the runbook.

### Neutral

- The choice does not affect the application code: the `PolicyGeneratorClient` HTTP boundary is identical across ECS-on-EC2 and EKS.
- A future move to a managed inference offering (Bedrock, SageMaker) is rejected per Principle XIII; this ADR does not relitigate that.
- The CPU-fallback profile's "behavior-equivalent under the contract test" property is asserted by ADR-0004's contract test, which runs across all `PolicyGeneratorClient` implementations including the llama.cpp adapter.

## Alternatives considered

### EKS with a GPU node group as the default

Rejected as the **default** but kept as a first-class alternative under a Terraform workspace flag. Reasons:

- ECS' operational surface is materially smaller than Kubernetes' for a single-team, single-workload-shape deployment. The Kubernetes-native primitives EKS exposes (NetworkPolicy, RBAC, Operator pattern) are not load-bearing for feature 001 scope; their cost is real (cluster lifecycle, controller manager, ingress controller, autoscaler tuning).
- Future features that share the GPU pool across multiple workloads (e.g., the LLM upgrade-path stub, an evaluation harness, an embeddings service) make EKS materially more attractive; the workspace-flag pattern lets that switch happen as a configuration change, not a refactor.

### SageMaker hosted endpoint for the SLM

Rejected. SageMaker abstracts away the decoding configuration and image pinning controls Principle XIV depends on; deterministic decoding under a pinned vLLM digest with a pinned weight SHA is not an idiomatic SageMaker setup. SageMaker's per-request cost at the SC-002 sustained throughput is also higher than ECS-on-EC2 at steady state.

### AWS Bedrock

Rejected. Violates Principle XIII's SLM-first stance directly: Bedrock is a frontier-LLM SaaS, opt-in only and gated by a constitution-amendment ADR. Not a feature-001 candidate.

### Lambda for the SLM

Rejected. Lambda's cold-start latency (multi-second on GPU-equivalent custom containers, never mind the GPU-availability constraint) is incompatible with SC-001 and Principle XI.

### `g4dn.xlarge` (T4, 16 GB) instead of `g5.2xlarge`

Rejected. 16 GB is too tight on bf16 weights (~14 GB) plus KV cache for any non-trivial batch size; the SLM container would either OOM under load or force batch-size-1 generation, breaking SC-002 throughput. `g5.xlarge` is also tight; `g5.2xlarge` is the practical floor.

### `p4d.24xlarge` or larger H100/H200 instances

Rejected. Premium hardware is unwarranted for a 7B SLM; cost-per-event would be dominated by idle. Re-evaluate if the model upgrades to a larger size, which would be a superseding ADR.

### Spot instances for the SLM ASG

Rejected at default. Spot interruption during generation would breach SC-001's tail latency. Spot becomes a candidate once CollectMind implements warm-handoff retry across the SLM service (a future feature).

## References

- Constitution Principle XIII (SLM-First) at `.specify/memory/constitution.md`
- Constitution Principle VI (Reproducible Local Dev and Deployment) at `.specify/memory/constitution.md`
- Constitution Principle IX (Security) at `.specify/memory/constitution.md`
- Constitution Principle XI (Performance SLOs) at `.specify/memory/constitution.md`
- ADR-0002 (default SLM and inference runtimes) at `docs/adr/0002-default-slm-qwen2-5-7b-instruct.md`
- ADR-0003 (constrained-decoding library, outlines) at `docs/adr/0003-constrained-decoding-library.md`
- ADR-0004 (deterministic-fingerprint stub) at `docs/adr/0004-fingerprint-stub.md`
- Plan, research note R-013 (the inline draft this ADR supersedes) at `specs/001-policy-loop-vertical-slice/research.md`
- Plan, project structure (compute module) at `specs/001-policy-loop-vertical-slice/plan.md`
- AWS ECS Capacity Providers documentation: <https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-capacity-providers.html>
- AWS GPU instance families overview: <https://docs.aws.amazon.com/dlami/latest/devguide/gpu.html>
