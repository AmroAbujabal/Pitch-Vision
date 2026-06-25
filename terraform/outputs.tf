output "api_url" {
  description = "Public HTTPS URL of the PitchVision API"
  value       = google_cloud_run_v2_service.api.uri
}

output "image_registry" {
  description = "Artifact Registry path — tag and push your image here"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/pitchvision/pitchvision-api"
}
