# Get the container image from Artifact Registry
# https://registry.terraform.io/providers/hashicorp/google/latest/docs/data-sources/artifact_registry_docker_image
data "google_artifact_registry_docker_image" "container-image-github-runners-manager" {
  project       = module.project.project_id
  location      = var.region
  repository_id = module.artifact-registry-container.name
  image_name    = "app:latest" # Defined in cloudbuild-container.template.yaml
  depends_on = [
    null_resource.build-github-runners-manager-container
  ]
}

# Deploy the GitHub Actions Runners manager service on Cloud Run
# https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_run_v2_service
resource "google_cloud_run_v2_service" "cloud_run_github_runners_manager" {
  project              = module.project.project_id
  name                 = "github-runners-manager-${local.region_shortnames[var.region]}"
  location             = var.region
  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = true

  template {
    service_account                  = module.service-account-cloud-run-github-runners-manager.email
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    max_instance_request_concurrency = var.github_runners_manager_max_instance_request_concurrency

    scaling {
      min_instance_count = var.github_runners_manager_min_instance_count
      max_instance_count = var.github_runners_manager_max_instance_count
    }

    containers {
      image = data.google_artifact_registry_docker_image.container-image-github-runners-manager.self_link

      resources {
        startup_cpu_boost = false
        limits = {
          cpu    = "1000m"
          memory = "512Mi"
        }
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        name  = "GOOGLE_CLOUD_ZONE"
        value = "${var.region}-${var.zone}"
      }

      env {
        name  = "GITHUB_RUNNER_GROUP"
        value = var.github_runner_group
      }

      env {
        name = "GITHUB_APP_ID"
        value_source {
          secret_key_ref {
            secret  = module.secret-manager.ids["github-app-id"]
            version = "latest"
          }
        }
      }

      env {
        name = "GITHUB_INSTALLATION_ID"
        value_source {
          secret_key_ref {
            secret  = module.secret-manager.ids["github-installation-id"]
            version = "latest"
          }
        }
      }

      env {
        name = "GITHUB_PRIVATE_KEY"
        value_source {
          secret_key_ref {
            secret  = module.secret-manager.ids["github-private-key"]
            version = "latest"
          }
        }
      }

      env {
        name = "GITHUB_WEBHOOK_SECRET"
        value_source {
          secret_key_ref {
            secret  = module.secret-manager.ids["github-webhook-secret"]
            version = "latest"
          }
        }
      }
    }
  }

  deletion_protection = false

  depends_on = [
    google_secret_manager_secret_version.secret-version-default,
    time_sleep.wait_for_service_account_cloud_run
  ]
}
