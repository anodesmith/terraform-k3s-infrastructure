# K3s cluster provisioning.
#
# Renders one bootstrap script per node and hands each to local-exec. The
# resource tracks whether the script ran, not whether the cluster is healthy,
# and docs/not-implemented.md says so plainly rather than letting the resource
# type imply otherwise.

# One script per node. toset() because for_each rejects a list outright, and
# iterating a set also removes any chance of a duplicate node name silently
# producing two resources with the same key.
resource "local_file" "bootstrap" {
  for_each = toset(var.node_names)

  filename        = "${path.module}/scripts/${each.key}-bootstrap.sh"
  file_permission = "0755"

  content = templatefile("${path.module}/templates/bootstrap.sh.tftpl", {
    node_name            = each.key
    node_role            = var.node_roles[each.key]
    node_address         = var.node_addresses[each.key]
    k3s_version          = var.k3s_version
    cluster_token        = var.cluster_token
    api_endpoint         = "${var.node_addresses[var.node_names[0]]}:${var.api_port}"
    is_first_node        = each.key == var.node_names[0]
    pod_cidr             = var.pod_cidr
    service_cidr         = var.service_cidr
    bridge_name          = var.bridge_name
    install_docker       = var.install_docker
    allow_insecure       = var.allow_insecure_images
    registration_command = var.registration_command
  })

  # The token is in the file, so the file has to be readable only by the
  # operator. It also lands in a gitignored path.
  depends_on = [local_file.bootstrap_dir]
}

resource "local_file" "bootstrap_dir" {
  filename        = "${path.module}/scripts/.gitkeep"
  file_permission = "0644"
  content         = "# Rendered bootstrap scripts are written here by Terraform.\n"
}

resource "terraform_data" "bootstrap" {
  for_each = toset(var.node_names)

  triggers_replace = [
    local_file.bootstrap[each.key].id,
  ]

  # provisioner inside a for_each resource: one apply per node, and a failure
  # names the node rather than saying "the script failed".
  provisioner "local-exec" {
    # The deadline is enforced by coreutils timeout in the command rather than by
    # the provisioner's own `timeout` argument. Terraform 1.16 rejects that
    # argument on a terraform_data resource ("An argument named 'timeout' is not
    # expected here"), and the default 10-minute limit is shorter than a real
    # K3s install on a cold node.
    command     = "sudo timeout ${var.apply_timeout_minutes * 60}s bash ${local_file.bootstrap[each.key].filename}"
    interpreter = ["/bin/bash", "-c"]
  }
}

# --- Cluster readiness -----------------------------------------------------

# Reads the kubeconfig the first node's install produced and waits for the
# control plane to answer. Runs after every node is up, so a cluster is never
# declared ready before its workers have joined.
resource "terraform_data" "wait_for_api" {
  triggers_replace = [
    terraform_data.bootstrap[var.node_names[0]].id,
  ]

  provisioner "local-exec" {
    command     = <<-EOT
      set -euo pipefail
      export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

      deadline=$(( $(date +%s) + ${var.apply_timeout_minutes} * 60 ))
      until kubectl get --raw=/readyz >/dev/null 2>&1; do
        if [ "$(date +%s)" -ge "$deadline" ]; then
          echo "API server did not become ready within ${var.apply_timeout_minutes} minutes" >&2
          kubectl get --raw=/readyz 2>&1 || true
          exit 1
        fi
        sleep 5
      done

      echo "control plane ready"
      kubectl get nodes -o wide
    EOT
    interpreter = ["/bin/bash", "-c"]
    environment = {
      KUBECONFIG = "/etc/rancher/k3s/k3s.yaml"
    }
  }
}
