# Not implemented, and what is not verified

## Not verified without a Linux host

`terraform validate` passes on the build machine, and `terraform fmt` is clean.
That is real semantic validation of the module tree. It is not an apply.

### Cannot be verified without a target

| Gap | Why it matters | How to close it |
|---|---|---|
| `terraform plan` | Variables, locals and provider schemas are checked; a real plan additionally evaluates them against an API | `terraform plan` against a real or mocked backend |
| Provisioner execution | Every `local-exec` in this config is unexecuted. A typo in a rendered script is invisible to validate | `terraform apply` on a throwaway host |
| The bridge script is idempotent | It is written to be, and it reconciles rather than recreates, but nothing has confirmed it | Apply twice, diff the second plan |
| K3s actually joins | The readiness provisioner polls `/readyz`; it has never run | Apply against a real node |
| Cloud IAM for the S3 backend | `environments/lab/backend.hcl` names a bucket that does not exist | Provision the bucket, or point at LocalStack |
| Provider download integrity | `init` verifies HashiCorp's published checksums, not that you trust the registry | Pin to a mirror, verify signatures |

### The one thing worth doing first

```bash
terraform init -backend-config=environments/lab/backend.hcl
terraform plan -var-file=environments/lab/terraform.tfvars
```

Then, on a throwaway Debian host:

```bash
sudo terraform apply -var-file=environments/lab/terraform.tfvars
sudo terraform apply -var-file=environments/lab/terraform.tfvars   # expect: no changes
```

That second apply is the single most informative observation available. It is
the only thing that proves the bridge reconciles rather than recreates, and
that `local_file` content is stable across runs.

## Not implemented, by design

### No cloud provider resources

There is not one `aws_instance`, `azurerm_linux_virtual_machine` or
`google_compute_instance` in this configuration. Nodes are addressed by
`cidrhost` and bootstrapped by a rendered script, because the point of the day
is the K3s and networking topology.

The honest consequence: **this configuration cannot create the machines it
describes.** It assumes a host exists at each address. A production version
would pair these modules with instance resources or, better, hand the node
inventory to Day 2's Ansible playbooks and let a real provisioner own the
lifecycle.

### `tls_private_key.cluster_ca` is generated and unused

It exists to show the provider pattern and is marked sensitive. Nothing
consumes it, because K3s generates its own CA during install. A reviewer should
read it as dead weight rather than as certificate management.

### No remote state bootstrap

`environments/lab/backend.hcl` points at `infra-lab-terraform-state`. Creating
that bucket, versioning it, and locking it is out of scope. `use_lockfile` is
set, which is the part that matters: two concurrent applies against one state
file corrupt it in ways that are not always obvious.

### No K3s configuration manifests

Only `--disable=traefik` and `--disable=servicelb` are passed. There is no
`--write-kubeconfig`, no kubelet arguments, no custom
`/etc/rancher/k3s/config.yaml`. Deploying workloads is Day 5's and Day 6's job.

### No Helm releases

Not a single `helm_release`. Installing a chart from Terraform and then managing
the same resource with kubectl is how two controllers fight over one object. If
Helm is added later it should own everything it installs, exclusively.

### No Cluster API

K3s is bootstrapped by a shell script, not by cluster-api or the k3s-upgrade
provider. Declarative cluster *lifecycle* (add a node, upgrade a version) is
real IaC work that this does not attempt.

### No policy-as-code scanning

`tfsec` and `checkov` are not wired in, despite the configuration containing
things they would flag. They are the obvious next addition, and they belong in
the nightly pipeline rather than in a manual pre-commit hook.

## Known limitations of what is implemented

### The bridge MTU is a single global value

One MTU for the whole cluster, chosen by environment. A cluster spanning
mixed-underlay fabrics needs per-node MTU, and a mismatch between node MTU and
the bridge MTU produces exactly the kind of "pods can reach each other but not
the internet" fault that takes an afternoon to find.

### `node_cidr` host addresses start at 10

Addresses are `cidrhost(node_cidr, 10 + index)`, reserving .1 and .2 for the
gateway and the bridge. A node count high enough to run past the end of the
subnet produces a `cidrhost` failure at plan time rather than a clear message
about the subnet being too small. The variable validation checks that
`node_cidr` parses, not that it is large enough for the node count.

### The readiness wait only covers the control plane

`terraform_data.wait_for_api` polls `/readyz` and prints `kubectl get nodes`. It
does not assert that the expected *number* of nodes reached `Ready`, so a worker
that failed to join still results in a successful apply. The node count is
known at plan time and should be asserted.

### The `bastion` concept from Day 2 does not carry over

This configuration has no bastion and no jump host. Node addresses are directly
reachable, which is fine on a lab bridge and wrong in production. If
`registration_command` points at an internal mirror, a bastion becomes
necessary.

### `enable_docker_install` defaults to false and is a trap if enabled

K3s ships its own containerd. Installing Docker alongside it gives you two
container runtimes, and the one that ends up being used depends on the
`crictl` versus `docker` default rather than on any deliberate choice. The
variable exists because some lab tooling assumes Docker, and the bootstrap
script logs a warning when it is on.
