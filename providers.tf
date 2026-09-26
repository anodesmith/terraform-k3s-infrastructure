terraform {
  # Remote state. Partial configuration: bucket, key and region come from
  # -backend-config so the same code initialises against dev, lab and prod
  # without editing this file.
  #
  # The local backend is NOT a fallback. A commented-out local backend here is
  # how two engineers end up with two completely different ideas of what
  # infrastructure exists. Failing to find the remote state is the correct
  # behaviour.
  backend "s3" {}
}

provider "random" {}

# The local provider renders files on the control node. Used for artefacts that
# are inputs to other tools rather than state that Terraform needs to track.
provider "local" {}

# Used for the generated join token and node password. Marked sensitive because
# these end up in a node's bootstrap script, and Terraform state is not a
# secret store.
provider "tls" {}

# Points at the K3s API server created by this configuration.
#
# left unset, the kubernetes provider reads KUBE_CONFIG_PATH. That is the
# default because a chicken-and-egg problem exists otherwise: the provider needs
# credentials that the resources it manages are what create.
provider "kubernetes" {
  # Intentionally empty. Configured via KUBE_CONFIG_PATH.
  #
  # host                   = var.k8s_endpoint
  # client_certificate     = var.k8s_client_cert_b64
  # client_key             = var.k8s_client_key_b64
  insecure = false
}
