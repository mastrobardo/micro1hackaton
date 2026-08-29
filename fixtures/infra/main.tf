# Northwind Airlines — SkyRoute connector infrastructure (fictional).
# `terraform validate` clean; no provider credentials required.

terraform {
  required_version = ">= 1.5"
}

locals {
  project = "northwind-skyroute-connector"
  tags = {
    Client  = "Northwind Airlines"
    Vendor  = "SkyRoute Data Ltd"
    Region  = var.aws_region
    Account = var.aws_account_id
  }
}

resource "null_resource" "skyroute_connector" {
  triggers = {
    project        = local.project
    region         = var.aws_region
    account        = var.aws_account_id
    ingress_cidr   = var.skyroute_ingress_cidr
    upstream       = "api.northwind-internal.net"
    internal_peers = "booking-core,pricing-svc,fare-cache"
  }
}

output "connector_id" {
  value = null_resource.skyroute_connector.id
}
