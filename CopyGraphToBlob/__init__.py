import logging
import os
import azure.functions as func
import requests
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceExistsError

STORAGE_ACCOUNT_NAME = os.environ.get("STORAGE_ACCOUNT_NAME")

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("CopyGraphToBlob function started.")

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON body", status_code=400)

    download_url = req_body.get("downloadUrl")
    container_name = req_body.get("containerName")
    blob_name = req_body.get("blobName", "recording.mp4")

    if not download_url or not container_name:
        return func.HttpResponse("Missing downloadUrl or containerName", status_code=400)

    if not STORAGE_ACCOUNT_NAME:
        return func.HttpResponse("Missing STORAGE_ACCOUNT_NAME in settings", status_code=500)

    try:
        # Autenticação via Managed Identity / VSCode login / Azure CLI
        credential = DefaultAzureCredential()
        blob_service_client = BlobServiceClient(
            f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
            credential=credential
        )

        container_client = blob_service_client.get_container_client(container_name)
        try:
            container_client.create_container()
            logging.info(f"Created container: {container_name}")
        except ResourceExistsError:
            logging.info(f"Container already exists: {container_name}")

        blob_client = container_client.get_blob_client(blob_name)

        # Streaming download -> upload (não carrega todo arquivo na memória)
        with requests.get(download_url, stream=True) as response:
            response.raise_for_status()
            # response.raw é um file-like object; upload_blob aceita stream
            blob_client.upload_blob(response.raw, overwrite=True)

        return func.HttpResponse(f"Uploaded to {container_name}/{blob_name}", status_code=200)

    except Exception as e:
        logging.exception("Error copying file to blob")
        return func.HttpResponse(f"Error: {str(e)}", status_code=500)
