variable "name" {
  description = "Short name used in Azure resource names."
  type        = string
  default     = "webpagedb"
}

variable "resource_group_name" {
  description = "Existing resource group to deploy into."
  type        = string
  default     = "rg-webpagedb"
}

variable "running" {
  description = "true runs the web app, false removes it. The database is always kept."
  type        = bool
}

variable "image" {
  description = "Full image reference. Required when running = true."
  type        = string
  default     = ""
}

variable "min_replicas" {
  description = "0 scales to zero when idle (cheapest, short cold start). 1 keeps it warm."
  type        = number
  default     = 0
}

variable "postgres_server_name" {
  description = "Globally unique Postgres server name. Set by scripts/bootstrap-azure.sh."
  type        = string
}

variable "postgres_version" {
  description = "Major Postgres version. Keep in step with compose.yaml."
  type        = string
  default     = "17"
}

variable "postgres_sku" {
  description = "Server size. Burstable B1ms is the smallest."
  type        = string
  default     = "B_Standard_B1ms"
}
