import logging
from fastapi import FastAPI, Request
import httpx

app = FastAPI()
logger = logging.getLogger(__name__)

AIRFLOW_API = "http://airflow-webserver.llmops.svc.cluster.local:8080/api/v1"
AIRFLOW_USER = "admin"
AIRFLOW_PASS = "admin"

@app.post("/webhook/blob-created")
async def blob_created(request: Request):
    events = await request.json()

    for event in events:
        # Respond to Event Grid validation handshake
        if event.get("eventType") == "Microsoft.EventGrid.SubscriptionValidationEvent":
            return {"validationResponse": event["data"]["validationCode"]}

        if event.get("eventType") == "Microsoft.Storage.BlobCreated":
            blob_url  = event["data"]["url"]
            blob_name = blob_url.split("/raw-documents/")[-1]

            logger.info(f"Triggering ingestion DAG for: {blob_name}")

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{AIRFLOW_API}/dags/document_ingestion_pipeline/dagRuns",
                    json={
                        "dag_run_id": f"event_{event['id']}",
                        "conf": {
                            "blob_name":      blob_name,
                            "container_name": "raw-documents"
                        }
                    },
                    auth=(AIRFLOW_USER, AIRFLOW_PASS)
                )
                logger.info(f"DAG trigger response: {resp.status_code}")

    return {"status": "accepted"}
