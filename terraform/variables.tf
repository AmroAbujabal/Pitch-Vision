variable "project_id" {
  description = "Google Cloud project ID (e.g. pitchvision-prod)"
  type        = string
}

variable "region" {
  description = "Cloud Run deployment region"
  type        = string
  default     = "us-central1"
}

variable "image_tag" {
  description = "Docker image tag to deploy (e.g. latest, v0.1.0)"
  type        = string
  default     = "latest"
}

variable "secret_key" {
  description = "JWT signing secret — keep this out of version control"
  type        = string
  sensitive   = true
}

variable "database_url" {
  description = "PostgreSQL connection string (sqlite:// will NOT work on Cloud Run)"
  type        = string
  sensitive   = true
}

variable "redis_url" {
  description = "Redis connection string for Celery broker"
  type        = string
  default     = "redis://localhost:6379/0"
  sensitive   = true
}
