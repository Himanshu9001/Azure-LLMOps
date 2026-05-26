"""
Submit QLoRA training job to Azure ML.
Run this locally after GPU quota is approved.
"""
from azure.ai.ml import MLClient, load_job
from azure.identity import DefaultAzureCredential

SUBSCRIPTION_ID  = "e56f284c-4b28-4a6a-a473-12e5eaea726e"
RESOURCE_GROUP   = "rg-llmops-prod"
WORKSPACE_NAME   = "llmops-ml-workspace"

def submit():
    # Authenticate using your az login session
    ml_client = MLClient(
        DefaultAzureCredential(),
        SUBSCRIPTION_ID,
        RESOURCE_GROUP,
        WORKSPACE_NAME
    )

    # Load job definition
    job = load_job("training/azure_ml/job.yaml")

    # Submit
    returned_job = ml_client.jobs.create_or_update(job)
    print(f"Job submitted: {returned_job.name}")
    print(f"Studio URL: {returned_job.studio_url}")

    # Stream logs
    ml_client.jobs.stream(returned_job.name)

if __name__ == "__main__":
    submit()