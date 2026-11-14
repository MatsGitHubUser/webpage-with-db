output "url" {
  description = "Public URL, or \"stopped\" when the web app is not running."
  value       = var.running ? "https://${azurerm_container_app.web[0].ingress[0].fqdn}" : "stopped"
}
