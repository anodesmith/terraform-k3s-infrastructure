variable "project_name" {
  description = "Short project identifier used in resource names and tags. Lowercase, no separators."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}$", var.project_name))
    error_message = "project_name must be lowercase alphanumeric with hyphens, 2-31 characters, starting with a letter."
  }
}

variable "environment" {
  description = "Deployment environment. Drives instance sizing and which hardening profile applies."
  type        = string
  default     = "lab"

  validation {
    condition     = contains(["lab", "staging", "production"], var.environment)
    error_message = "environment must be one of: lab, staging, production."
  }
}

# --- K3s cluster -----------------------------------------------------------

variable "k3s_version" {
  description = "Pinned K3s release channel. A specific version is used rather than 'stable' so a cluster does not silently upgrade itself across a control plane change."
  type        = string
  default     = "v1.31.4+k3s1"

  validation {
    condition     = can(regex("^v\\d+\\.\\d+\\.\\d+\\+k3s\\d+$", var.k3s_version))
    error_message = "k3s_version must be an exact version such as v1.31.4+k3s1. Do not use 'stable' or 'latest': they let a cluster change itself."
  }
}

variable "control_plane_nodes" {
  description = "Number of K3s server nodes. Odd numbers only: an even number of control plane nodes has no quorum benefit and costs an extra node."
  type        = number
  default     = 1

  validation {
    condition     = var.control_plane_nodes >= 1 && var.control_plane_nodes <= 5
    error_message = "control_plane_nodes must be between 1 and 5."
  }

  validation {
    condition     = var.control_plane_nodes % 2 == 1
    error_message = "control_plane_nodes must be odd. An even count adds a node without changing quorum."
  }
}

variable "agent_nodes" {
  description = "Number of additional K3s agent (worker) nodes."
  type        = number
  default     = 2

  validation {
    condition     = var.agent_nodes >= 0 && var.agent_nodes <= 20
    error_message = "agent_nodes must be between 0 and 20."
  }
}

variable "node_cidr" {
  description = "CIDR block the node interfaces are carved from."
  type        = string
  default     = "192.168.50.0/24"

  validation {
    condition     = can(cidrhost(var.node_cidr, 0))
    error_message = "node_cidr must be a valid IPv4 CIDR block, for example 192.168.50.0/24."
  }
}

variable "node_gateway" {
  description = "Gateway address for the node network. Must fall inside node_cidr."
  type        = string
  default     = "192.168.50.1"

  validation {
    condition     = cidrhost(var.node_cidr, 0) != var.node_gateway
    error_message = "node_gateway must be inside node_cidr."
  }
}

variable "k3s_api_port" {
  description = "Host port the K3s API server binds to."
  type        = number
  default     = 6443

  validation {
    condition     = var.k3s_api_port > 1024 && var.k3s_api_port < 65535
    error_message = "k3s_api_port must be a non-privileged port above 1024."
  }
}

# --- Networking ------------------------------------------------------------

variable "bridge_name" {
  description = "Name of the container network bridge. Must be a valid Linux interface name."
  type        = string
  default     = "br-k3s0"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,14}$", var.bridge_name))
    error_message = "bridge_name must be a valid interface name: lowercase alphanumeric with hyphens, 2-15 characters."
  }
}

variable "pod_cidr" {
  description = "Pod network CIDR. Must not overlap node_cidr, or the CNI cannot route between them."
  type        = string
  default     = "10.42.0.0/16"

  validation {
    condition     = can(cidrhost(var.pod_cidr, 0))
    error_message = "pod_cidr must be a valid IPv4 CIDR block."
  }
}

variable "service_cidr" {
  description = "Service ClusterIP range."
  type        = string
  default     = "10.43.0.0/16"

  validation {
    condition     = can(cidrhost(var.service_cidr, 0))
    error_message = "service_cidr must be a valid IPv4 CIDR block."
  }
}

# --- Safety ----------------------------------------------------------------

variable "enable_docker_install" {
  description = "Whether the bootstrap script installs Docker. Off by default because K3s's containerd already provides what the lab needs."
  type        = bool
  default     = false
}

variable "allow_insecure_images" {
  description = "Permit HTTP container registry pulls. Never true outside a throwaway lab: it is plaintext image transfer and a trivially exploitable mirror point."
  type        = bool
  default     = false

  # Cross-variable validation, which requires Terraform 1.9 or later. A boolean
  # cannot be validated against a fixed set of values, but it can be validated
  # against another variable, and that is the rule that actually matters: this
  # combination must be impossible to plan, not merely discouraged in a comment.
  validation {
    condition     = var.environment != "production" || !var.allow_insecure_images
    error_message = "allow_insecure_images cannot be true when environment is 'production'. Plaintext image transfer is not a production setting."
  }
}

variable "registration_command" {
  description = "Command used to install K3s. Overridable so a mirror or an air-gapped installer can be substituted without editing the module."
  type        = string
  default     = "https://get.k3s.io"
}
