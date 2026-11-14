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
  description = "true runs the web app, false removes it. The comment storage is always kept."
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

variable "location" {
  description = <<-EOT
    Azure region for the comment storage and the web app. It differs from the
    resource group's region (Sweden Central) because the subscription may have
    only one Container Apps environment in total, and cae-webpagedb was created
    here. Changing this after creation replaces the storage account and loses
    the comments, which prevent_destroy blocks.
  EOT
  type        = string
  default     = "northeurope"
}
