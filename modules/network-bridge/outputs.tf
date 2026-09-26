# Outputs, kept out of main.tf so the resource definitions and the interface
# are readable separately.

output "bridge_name" {
  description = "Name of the bridge interface."
  value       = var.bridge_name
}

output "bridge_address" {
  description = "Address assigned to the bridge."
  value       = local.bridge_address
}

output "bridge_cidr" {
  description = "Subnet assigned to the bridge."
  value       = var.bridge_cidr
}

output "bridge_gateway" {
  description = "Default gateway for the bridge subnet."
  value       = var.gateway
}

output "mtu" {
  description = "Configured MTU on the bridge."
  value       = var.mtu
}

output "nat_enabled" {
  description = "Whether a masquerade rule was installed for the bridge subnet."
  value       = var.enable_nat
}
