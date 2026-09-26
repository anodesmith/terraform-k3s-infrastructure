locals {
  # Common tags, merged onto everything. The component tag is what makes
  # terraform output and cost reporting readable at a glance.
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Repository  = "day03-terraform-k3s-infrastructure"
  }

  # Every node address, control plane first.
  all_nodes = concat(
    [for i in range(var.control_plane_nodes) : format("server-%02d", i + 1)],
    [for i in range(var.agent_nodes) : format("agent-%02d", i + 1)],
  )

  # Address assigned to each node. Index 0 and 1 are reserved for the gateway
  # and the bridge, which is why host numbers start at 10.
  node_addresses = {
    for idx, name in local.all_nodes :
    name => cidrhost(var.node_cidr, 10 + idx)
  }

  # Per-node role, used to decide --server versus --agent on the install line.
  node_roles = {
    for idx, name in local.all_nodes :
    name => idx < var.control_plane_nodes ? "server" : "agent"
  }

  # Generated once and shared. A separate token per node would let one
  # compromised worker join as a control plane node.
  cluster_token = random_password.cluster_token.result

  k3s_api_endpoint = "${local.node_addresses[local.all_nodes[0]]}:${var.k3s_api_port}"

  # Artefacts land here so an operator can read what Terraform is about to
  # execute before it executes it. Gitignored, because the rendered scripts
  # contain the cluster token.
  artifact_dir = "${path.module}/artifacts"
}
