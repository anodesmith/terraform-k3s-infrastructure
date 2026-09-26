variable "bridge_name" {
  description = "Interface name for the bridge. Must be a valid Linux interface name."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,14}$", var.bridge_name))
    error_message = "bridge_name must be lowercase alphanumeric with hyphens, 2-15 characters."
  }
}

variable "bridge_cidr" {
  description = "Subnet assigned to the bridge interface."
  type        = string

  validation {
    condition     = can(cidrhost(var.bridge_cidr, 0))
    error_message = "bridge_cidr must be a valid IPv4 CIDR block."
  }
}

variable "gateway" {
  description = "Default gateway address for the bridge subnet."
  type        = string
}

variable "mtu" {
  description = "MTU for the bridge. 1400 for a lab because it survives nested virtualisation, where 1500 does not."
  type        = number
  default     = 1500

  validation {
    condition     = var.mtu >= 1200 && var.mtu <= 9000
    error_message = "mtu must be between 1200 and 9000."
  }
}

variable "enable_nat" {
  description = "Install a masquerade rule so bridge traffic can leave the host."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags applied to created resources."
  type        = map(string)
  default     = {}
}
