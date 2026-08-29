variable "aws_region" {
  description = "Deploy region for the Northwind API"
  type        = string
  default     = "nwa-prod-eu-west-1"
}

variable "aws_account_id" {
  description = "Northwind Airlines production account"
  type        = string
  default     = "447015923388"
}

variable "skyroute_ingress_cidr" {
  description = "Management host allowed to reach the SkyRoute connector"
  type        = string
  default     = "10.20.4.7/32"
}
