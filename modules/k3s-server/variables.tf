variable "project_name" {
  description = "Project identifier, used in resource naming."
  type        = string
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "lab"
}

variable "node_names" {
  description = "Names of the nodes in this cluster."
  type        = list(string)

  validation {
    condition     = length(var.node_names) > 0
    error_message = "node_names must contain at least one node."
  }
}

variable "node_addresses" {
  description = "Map of node name to IP address."
  type        = map(string)
}

variable "node_roles" {
  description = "Map of node name to role: 'server' or 'agent'."
  type        = map(string)

  validation {
    condition     = alltrue([for r in values(var.node_roles) : contains(["server", "agent"], r)])
    error_message = "Every node role must be either 'server' or 'agent'."
  }
}

variable "pod_cidr" {
  description = "Pod network CIDR."
  type        = string
}

variable "service_cidr" {
  description = "Service ClusterIP range."
  type        = string
}

variable "k3s_version" {
  description = "Exact pinned K3s version."
  type        = string
}

variable "api_port" {
  description = "Host port for the API server."
  type        = number
  default     = 6443
}

variable "cluster_token" {
  description = "Shared cluster join token. Marked sensitive so it is redacted from Terraform output and plan logs."
  type        = string
  sensitive   = true
}

variable "bridge_name" {
  description = "Bridge interface the nodes attach to."
  type        = string
}

variable "install_docker" {
  description = "Install Docker alongside containerd. Off by default."
  type        = bool
  default     = false
}

variable "allow_insecure_images" {
  description = "Permit HTTP registry pulls. Lab only."
  type        = bool
  default     = false
}

variable "registration_command" {
  description = "K3s installation script URL. Overridable for mirrors and air-gapped installs."
  type        = string
  default     = "https://get.k3s.io"
}

variable "tags" {
  description = "Tags applied to created resources."
  type        = map(string)
  default     = {}
}

variable "apply_timeout_minutes" {
  description = "How long to wait for the bootstrap script before giving up."
  type        = number
  default     = 20
}
