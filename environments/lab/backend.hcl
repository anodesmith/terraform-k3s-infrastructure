# Partial backend configuration for the lab environment.
#
#   terraform init -backend-config=environments/lab/backend.hcl
#
# No credentials here. Authentication comes from the environment
# (AWS_ACCESS_KEY_ID, AWS_PROFILE, or an instance role), never from a file in
# the repository.

bucket = "infra-lab-terraform-state"
key    = "day03/k3s/terraform.tfstate"
region = "eu-west-1"

encrypt = true

# Locking prevents two people writing state at once, which corrupts it in ways
# that are not always obvious.
use_lockfile = true
