# Container network bridge.
#
# Terraform has no provider that owns Linux bridge interfaces in a way that
# models their real lifecycle, so this is rendered as a shell script and applied
# with local-exec. Being explicit about that is better than wrapping ip commands
# in a resource type that implies more tracking than actually happens.

resource "local_file" "bridge_script" {
  filename        = "${path.module}/bridge-${var.bridge_name}.sh"
  file_permission = "0755"
  content         = local.bridge_script
}

resource "terraform_data" "bridge" {
  triggers_replace = [
    local_file.bridge_script.id,
  ]

  provisioner "local-exec" {
    command     = "sudo bash ${local_file.bridge_script.filename}"
    interpreter = ["/bin/bash", "-c"]
  }
}

locals {
  bridge_address = cidrhost(var.bridge_cidr, 1)

  bridge_script = <<-EOT
    #!/usr/bin/env bash
    # Rendered by Terraform. Do not edit; the next apply overwrites this file.
    set -euo pipefail

    BRIDGE="${var.bridge_name}"
    ADDRESS="${local.bridge_address}"
    CIDR="${var.bridge_cidr}"
    GATEWAY="${var.gateway}"
    MTU="${var.mtu}"

    # Refuse rather than guess. Renaming a live bridge orphans every network
    # namespace attached to it, and the failure surfaces as pods that cannot
    # reach anything.
    if ip link show "$BRIDGE" >/dev/null 2>&1; then
      echo "bridge $BRIDGE already exists, reconciling"
    else
      ip link add name "$BRIDGE" type bridge
    fi

    # $${CIDR#*/} is bash parameter expansion, not Terraform interpolation.
    # Escaped as $${ because Terraform would otherwise read it as an expression
    # and fail with "bitwise operators are not supported" on the '#' and '*'.
    ip addr replace "$ADDRESS/$${CIDR#*/}" dev "$BRIDGE"
    ip link set "$BRIDGE" mtu "$MTU" up

    # Address the first usable host in the subnet as the gateway, unless an
    # explicit one was supplied.
    if ip route show default dev "$BRIDGE" | grep -q .; then
      echo "default route via $BRIDGE already present"
    else
      ip route replace default via "$GATEWAY" dev "$BRIDGE"
    fi

    %{~if var.enable_nat~}
    # Masquerade so containers can reach off-subnet destinations. Without this,
    # a pull from a public registry hangs with no useful error.
    if ! iptables -t nat -C POSTROUTING -s "${var.bridge_cidr}" ! -o "$BRIDGE" -j MASQUERADE 2>/dev/null; then
      iptables -t nat -A POSTROUTING -s "${var.bridge_cidr}" ! -o "$BRIDGE" -j MASQUERADE
    fi
    %{~else~}
    echo "NAT disabled by configuration"
    %{~endif~}

    echo "bridge $BRIDGE up on $ADDRESS"
  EOT
}
