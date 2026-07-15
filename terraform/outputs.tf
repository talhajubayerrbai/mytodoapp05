# ---------------------------------------------------------------------------
# ALB DNS — prefer the live ingress hostname; fall back to AWS API lookup
# ---------------------------------------------------------------------------

# Look up the ALB created by the ingress controller via its cluster tag.
# This is resilient when Terraform state doesn't yet have the ingress status
# populated (e.g. because wait_for_rollout = false).
data "aws_lb" "app" {
  tags = {
    "elbv2.k8s.aws/cluster" = "${var.project_name}-cluster"
  }

  # The ALB may not exist on the very first apply (before the ingress
  # controller has provisioned it). We wrap the whole output in try() so
  # plan/apply never fails because of this lookup.
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer created by the Ingress"
  # Prefer the Kubernetes ingress status (populated on subsequent applies),
  # then the live AWS data-source lookup, then empty string as last resort.
  value = coalesce(
    try(kubernetes_ingress_v1.app.status[0].load_balancer[0].ingress[0].hostname, ""),
    try(data.aws_lb.app.dns_name, ""),
    ""
  )
}
