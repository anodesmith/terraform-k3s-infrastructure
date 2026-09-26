# Root configuration: a K3s cluster on container network bridges.
#
#   terraform init -backend-config=environments/lab/backend.hcl
#   terraform plan
#   terraform apply
#
# Node "provisioning" here means rendering a bootstrap script and handing it to
# local-exec. That is deliberate: K3s has no Terraform provider that installs a
# cluster, and pretending otherwise would mean shelling out anyway while hiding
# it behind a resource type that implies Terraform is tracking the outcome.
# The resource tracks the script's execution, not the cluster's health.

# --- Cluster credentials ---------------------------------------------------

resource "random_password" "cluster_token" {
  length  = 64
  special = false

  # Alphanumeric only. A token containing shell metacharacters is a shell
  # injection into every bootstrap command that interpolates it.
  upper            = true
  lower            = true
  numeric          = true
  override_special = "/@"
}

resource "tls_private_key" "cluster_ca" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

# --- Network bridge --------------------------------------------------------

module "network_bridge" {
  source = "./modules/network-bridge"

  bridge_name = var.bridge_name
  bridge_cidr = cidrsubnet(var.node_cidr, 1, 0)
  gateway     = var.node_gateway
  mtu         = local.common_tags.Environment == "lab" ? 1400 : 1500
  enable_nat  = true

  tags = local.common_tags
}

# --- K3s control plane and agents -----------------------------------------

module "k3s_server" {
  source = "./modules/k3s-server"

  project_name = var.project_name
  environment  = var.environment
  node_names   = slice(local.all_nodes, 0, var.control_plane_nodes)
  node_addresses = {
    for name in slice(local.all_nodes, 0, var.control_plane_nodes) :
    name => local.node_addresses[name]
  }
  node_roles    = local.node_roles
  pod_cidr      = var.pod_cidr
  service_cidr  = var.service_cidr
  k3s_version   = var.k3s_version
  api_port      = var.k3s_api_port
  cluster_token = random_password.cluster_token.result
  bridge_name   = var.bridge_name

  install_docker        = var.enable_docker_install
  allow_insecure_images = var.allow_insecure_images
  registration_command  = var.registration_command

  tags = local.common_tags
}

# --- Artefacts written for inspection --------------------------------------

# The per-node bootstrap scripts are rendered by the k3s-server module, which
# owns the template. This writes a combined view of the node inventory so an
# operator can see the topology Terraform is about to build without having to
# join the output modules by hand.
resource "local_file" "inventory" {
  filename        = "${local.artifact_dir}/nodes.json"
  file_permission = "0644"
  content = jsonencode({
    for name in local.all_nodes :
    name => {
      address = local.node_addresses[name]
      role    = local.node_roles[name]
    }
  })
}

output "bootstrap_script_path" {
  description = "Paths of the rendered per-node bootstrap scripts. Read one before running it."
  value       = module.k3s_server.bootstrap_scripts
}
