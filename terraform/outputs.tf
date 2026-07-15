output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer created by the Ingress"
  value       = try(kubernetes_ingress_v1.app.status[0].load_balancer[0].ingress[0].hostname, "")
}
