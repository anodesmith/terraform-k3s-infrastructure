# Outputs. Anything a later stage of the pipeline needs, and nothing that is a
# secret.
#
# The cluster token is deliberately NOT an output. Terraform state holds it
# anyway, but an output puts it in `terraform output` in clear text, in CI logs,
# and in any terminal where someone runs the command to look at something else.

output "cluster_api_endpoint" {
  description = "K3s API server endpoint, reachable from the control node."
  value       = local.k3s_api_endpoint
}

output "bridge_interface" {
  description = "Name of the container network bridge that was created."
  value       = module.network_bridge.bridge_name
}

output "bridge_address" {
  description = "Address assigned to the container bridge."
  value       = module.network_bridge.bridge_address
}

output "node_inventory" {
  description = "Map of node name to address and control-plane/agent role."
  value       = { for name in local.all_nodes : name => local.node_addresses[name] }
}

output "control_plane_nodes" {
  description = "Names of the nodes running the control plane."
  value       = slice(local.all_nodes, 0, var.control_plane_nodes)
}

output "agent_nodes" {
  description = "Names of the worker-only nodes."
  value       = slice(local.all_nodes, var.control_plane_nodes, length(local.all_nodes))
}

output "pod_network" {
  description = "Pod CIDR, needed by any CNI-aware network policy written later."
  value       = var.pod_cidr
}

output "service_network" {
  description = "Service ClusterIP range."
  value       = var.service_cidr
}

output "node_inventory_path" {
  description = "Path to the generated node inventory JSON."
  value       = local_file.inventory.filename
}
