# Day 3 - Infrastructure as Code with Terraform & K3s

> Day 3 of 14 in the **Zero to Production Infrastructure & Security** series.

Declarative Terraform provisioning a K3s cluster on container network bridges,
verified with real `terraform validate` and a static policy suite that has been
proven to have teeth.

| | |
|---|---|
| **Day** | 3 of 14 |
| **Status** | Complete - 22 checks / 236 assertions, 21/21 negative tests |
| **Verification** | `terraform fmt -check -recursive && python tests/run_tests.py && python tests/negative_test.py` |
| **Tags** | `terraform` `k3s` `kubernetes` `iac` `hcl` |

## Usage

```bash
terraform init -backend-config=environments/lab/backend.hcl
terraform plan  -var-file=environments/lab/terraform.tfvars
terraform apply -var-file=environments/lab/terraform.tfvars
```

For a different environment, swap both paths. The backend is partial
configuration on purpose, so the same code initialises against dev, lab and
production without a line being edited.

## What validate caught

`terraform validate` is not decoration here. It found five real defects while
this was being written, all of which would have failed at apply time:

| Defect | Symptom |
|---|---|
| `var.k8s_api_endpoint` referenced, does not exist | Undeclared input variable |
| `for_each = var.node_names` on a list | Terraform rejects lists for `for_each`; needs `toset()` |
| `"${flags[@]}"` in a `templatefile` | `templatefile` evaluated it as Terraform: "invalid character" on `[` |
| `${CIDR#*/}` in a heredoc | Read as an expression; "bitwise operators are not supported" on `#` and `*` |
| Provisioner `timeout` on `terraform_data` | Rejected outright in Terraform 1.16 |

The last two share a root cause worth knowing: **bash and Terraform both use
`${...}`, and Terraform wins inside HCL.** Bash parameter and array expansion
has to be written `$${...}` inside a heredoc or a `.tftpl`. Both fixes are
commented in place, and the test suite enforces them.

## Design decisions

**`terraform_data` for anything with a provisioner.** A provisioner on a real
provider resource permanently taints that resource: change any argument and
Terraform destroys and recreates it. `terraform_data` exists to avoid exactly
this, and the suite asserts no managed resource carries a provisioner.

**No commented-out local backend.** It would be a one-line convenience and a
permanent trap. A commented `backend "local"` is how two engineers end up with
two different ideas of what infrastructure exists. Failing to find remote state
is the correct behaviour. The suite flags the pattern.

**Cross-variable validation on `allow_insecure_images`.** A boolean cannot be
validated against a set of allowed values, but Terraform 1.9+ can validate it
against *another* variable, so the genuinely dangerous combination -
`environment = "production"` with insecure images - is impossible to plan rather
than merely discouraged in a comment.

**Pinned K3s version, validated.** `k3s_version` must match an exact
`vX.Y.Z+k3sN` pattern. `stable` and `latest` are rejected by validation, because
a cluster that can upgrade itself across a control plane change is a cluster
that does so at the worst possible moment.

**Odd control plane count, validated.** An even count buys no additional quorum:
three and four nodes survive the same single failure. Validation rejects even
values rather than trusting a comment to explain why.

**The cluster token is not an output.** Terraform state holds it regardless, but
an output puts it in `terraform output`, in CI logs, and in whatever terminal
someone opened to look at something else. Rendered bootstrap scripts are written
to a gitignored directory with `0755` on the script and the token passed through
the environment, never interpolated into a command line where `ps` would show it.

**Sizing the lab bridge to 1400 MTU.** Nested virtualisation cannot carry 1500.
The production example keeps 1500, and the two are driven by the same variable
so the difference is a value rather than a fork.

## The test suite

`tests/run_tests.py` — 22 checks, 236 assertions, in two layers.

**Layer 1 is real Terraform.** `terraform fmt -check -recursive`, then
`terraform init -backend=false` followed by `terraform validate`, run against a
throwaway copy of the configuration so testing never leaves a `.terraform`
directory or lock file behind. `-backend=false` gets a full provider install
without needing remote state credentials.

**Layer 2 is static policy** for what validate does not look at: is every
variable documented and typed, is every provider pinned, is state gitignored
as a *rule* rather than a substring, is a secret variable marked `sensitive`, is
a module output missing from `outputs.tf`, is bash expansion escaped.

## The negative tests

`tests/negative_test.py` injects 21 known defects and asserts each is caught.
First run: **14 of 21**. The seven misses were all real, and four were bugs in
the checks themselves:

- **`.gitignore` substring check.** Searching for `*.tfstate` anywhere in the
  file is satisfied by `*.tfstate.*`, which does not match a file named
  `terraform.tfstate`. A real state file - which contains the cluster token -
  would still have been committable. Now matches rule lines only.
- **Substring check satisfied by a comment.** `check_security_variables_have_validation`
  tested for the word `validation`, and the comment above that variable explains
  what validation is for. It reported the block present *after* the negative test
  had deleted it. Fixed with a `has_attribute` helper, and the same latent flaw
  was removed from five other checks.
- **A regex that flagged correct code.** Tightening `has_attribute` to
  line-starts broke the inline map form `{ source = "...", version = "..." }`.
  The negative suite caught the regression immediately.
- **A check that could not work.** `for_each` on a list is caught definitively
  by `terraform validate`; a regex cannot see a variable's declared type. The
  check was **removed** rather than left giving false confidence, and
  `run_tests.py` says why.

All 21 pass now. The nightly verification runs both suites, so a check that
quietly stops matching is caught the same night.

## Layout

```
03-terraform-k3s-infrastructure/
  versions.tf              required_version + pinned providers
  providers.tf             provider blocks, partial s3 backend
  variables.tf             15 variables, all typed, documented and validated
  locals.tf                tags, node addressing, roles
  main.tf                  root module: token, bridge, cluster, artefacts
  outputs.tf
  modules/
    network-bridge/        bridge interface, idempotent, MTU-aware
    k3s-server/            per-node bootstrap, readiness wait
      templates/bootstrap.sh.tftpl
  environments/
    lab/                   terraform.tfvars + backend.hcl
    production/            .example only
  tests/
    run_tests.py           22 checks
    negative_test.py       21 injected defects
  docs/not-implemented.md
```

## Status

See [STATUS.md](STATUS.md) for the machine-written verification record and
[../_pipeline/PIPELINE_LOG.md](../_pipeline/PIPELINE_LOG.md) for the nightly
history.

## Licence

MIT. See [LICENSE](LICENSE).
