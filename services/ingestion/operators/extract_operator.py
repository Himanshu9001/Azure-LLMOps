import hashlib
import logging
from airflow.models import BaseOperator
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)

class ExtractOperator(BaseOperator):
    """
    Stage 1 — Download blob from ADLS Gen2, run OCR via Azure Document Intelligence.

    Uses prebuilt-layout model:
      - Preserves reading order across columns
      - Extracts tables as structured content
      - Returns page-by-page text with boundaries

    Authentication:
      - Storage: DefaultAzureCredential (Workload Identity on AKS)
      - Document Intelligence: API key from Key Vault env var
    """

    def __init__(
        self,
        blob_name: str,
        storage_account: str,
        container_name: str,
        doc_intelligence_endpoint: str,
        doc_intelligence_key: str,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.blob_name                 = blob_name
        self.storage_account           = storage_account
        self.container_name            = container_name
        self.doc_intelligence_endpoint = doc_intelligence_endpoint
        self.doc_intelligence_key      = doc_intelligence_key

    def execute(self, context: dict) -> dict:
        logger.info(f"Extracting: {self.blob_name}")

        # Workload Identity — no credentials needed on AKS
        credential = DefaultAzureCredential()

        # Download blob
        blob_client = BlobServiceClient(
            account_url=f"https://{self.storage_account}.blob.core.windows.net",
            credential=credential
        ).get_blob_client(
            container=self.container_name,
            blob=self.blob_name
        )
        content = blob_client.download_blob().readall()
        doc_hash = hashlib.sha256(content).hexdigest()
        logger.info(f"Downloaded {len(content)} bytes, hash={doc_hash[:8]}")

        # Azure Document Intelligence — prebuilt-layout
        doc_client = DocumentAnalysisClient(
            endpoint=self.doc_intelligence_endpoint,
            credential=AzureKeyCredential(self.doc_intelligence_key)
        )
        poller = doc_client.begin_analyze_document(
            model_id="prebuilt-layout",
            document=content
        )
        result = poller.result()

        # Extract page-by-page text
        pages = []
        for page in result.pages:
            page_text = " ".join(line.content for line in page.lines)
            pages.append({
                "page_number": page.page_number,
                "text":        page_text,
            })

        logger.info(f"Extracted {len(pages)} pages")

        return {
            "blob_name":  self.blob_name,
            "doc_hash":   doc_hash,
            "pages":      pages,
            "page_count": len(pages),
        }
