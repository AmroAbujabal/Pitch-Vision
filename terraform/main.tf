# ---------------------------------------------------------------------------
# Artifact Registry — Docker repository
# ---------------------------------------------------------------------------
# Stores the pitchvision-api Docker image.
# Push with:
#   gcloud auth configure-docker ${var.region}-docker.pkg.dev
#   docker tag pitchvision-api:latest \
#     ${var.region}-docker.pkg.dev/${var.project_id}/pitchvision/pitchvision-api:latest
#   docker push \
#     ${var.region}-docker.pkg.dev/${var.project_id}/pitchvision/pitchvision-api:latest

resource "google_artifact_registry_repository" "pitchvision" {
  repository_id = "pitchvision"
  format        = "DOCKER"
  location      = var.region
  description   = "PitchVision API Docker images"
}

# ---------------------------------------------------------------------------
# Cloud Run service — API
# ---------------------------------------------------------------------------

locals {
  image = "${var.region}-docker.pkg.dev/${var.project_id}/pitchvision/pitchvision-api:${var.image_tag}"
}

resource "google_cloud_run_v2_service" "api" {
  name     = "pitchvision-api"
  location = var.region

  template {
    containers {
      image = local.image

      # 1 vCPU, 2 GiB — sufficient for CPU inference with frame sampling.
      # Increase to 2 vCPU / 4 GiB for faster processing.
      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
        # CPU is only allocated while a request is being processed (cost saving).
        # Set to false if you run background Celery tasks inside this container.
        cpu_idle = true
      }

      env {
        name  = "SECRET_KEY"
        value = var.secret_key
      }
      env {
        name  = "DATABASE_URL"
        value = var.database_url
      }
      env {
        name  = "REDIS_URL"
        value = var.redis_url
      }
      env {
        name  = "DEVICE"
        value = "cpu"
      }
      env {
        name  = "DEFAULT_FPS"
        value = "25.0"
      }

      # Health check — Cloud Run uses the /health endpoint
      startup_probe {
        http_get {
          path = "/health"
          port = 8000
        }
        initial_delay_seconds = 10
        period_seconds        = 5
        failure_threshold     = 6
      }
    }

    # Scale to zero when idle (free tier friendly)
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
  }

  # Trigger a new revision on every apply (picks up image_tag changes)
  lifecycle {
    replace_triggered_by = [
      google_artifact_registry_repository.pitchvision
    ]
  }

  depends_on = [google_artifact_registry_repository.pitchvision]
}

# ---------------------------------------------------------------------------
# IAM — allow unauthenticated invocations
# The API enforces its own JWT auth; Cloud Run does not need to add another
# auth layer. Remove this if you want Google IAM as a second factor.
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
