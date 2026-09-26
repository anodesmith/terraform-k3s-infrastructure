# Outputs, kept out of main.tf so the resource definitions and the interface
# are readable separately.

output "node_names" {
  description = "Nodes provisioned by this module."
  value       = var.node_names
}

output "control_plane_nodes" {
  description = "Nodes running the control plane."
  value       = [for n, r in var.node_roles : n if r == "server"]
}

output "agent_nodes" {
  description = "Worker-only nodes."
  value       = [for n, r in var.node_roles : n if r == "agent"]
}

output "control_plane_ready" {
  description = "Whether the API server reached ready state during apply. Only meaningful after a real apply."
  value       = terraform_data.wait_for_api.id != ""
}

output "bootstrap_scripts" {
  description = "Map of node name to rendered bootstrap script path. Read one before running it: each contains the cluster token."
  value       = { for k, f in local_file.bootstrap : k => f.filename }
}

output "kubeconfig_path" {
  description = "Path to the kubeconfig written by the K3s install."
  value       = "/etc/rancher/k3s/k3s.yaml"
}
