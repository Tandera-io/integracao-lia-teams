import logging
import os
import json
import azure.functions as func
import requests
from msal import ConfidentialClientApplication
from urllib.parse import parse_qs

# Configurações do Microsoft Graph
CLIENT_ID = os.environ.get("MICROSOFT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("MICROSOFT_CLIENT_SECRET")
TENANT_ID = os.environ.get("MICROSOFT_TENANT_ID")
TRANSCRIPTION_API_URL = os.environ.get("TRANSCRIPTION_API_URL")
WEBHOOK_VALIDATION_TOKEN = os.environ.get("WEBHOOK_VALIDATION_TOKEN")

# Scopes necessários para o Microsoft Graph
SCOPES = ["https://graph.microsoft.com/.default"]

def get_graph_access_token():
    """Obtém um token de acesso para o Microsoft Graph usando credenciais de aplicativo."""
    try:
        app = ConfidentialClientApplication(
            CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{TENANT_ID}",
            client_credential=CLIENT_SECRET,
        )
        
        result = app.acquire_token_silent(SCOPES, account=None)
        if not result:
            result = app.acquire_token_for_client(scopes=SCOPES)
        
        if "access_token" in result:
            return result["access_token"]
        else:
            logging.error(f"Erro ao obter token: {result.get('error_description', 'Erro desconhecido')}")
            return None
    except Exception as e:
        logging.error(f"Exceção ao obter token: {str(e)}")
        return None

def get_recording_download_url(recording_id, access_token):
    """Obtém a URL de download de uma gravação usando o Microsoft Graph."""
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Endpoint para obter detalhes da gravação
        url = f"https://graph.microsoft.com/v1.0/communications/callRecords/{recording_id}/recordings"
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        # Procurar pela URL de download na resposta
        if "value" in data and len(data["value"]) > 0:
            recording = data["value"][0]
            download_url = recording.get("@microsoft.graph.downloadUrl")
            if download_url:
                return download_url
        
        logging.warning(f"URL de download não encontrada para recording_id: {recording_id}")
        return None
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro ao obter URL de download: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Exceção ao obter URL de download: {str(e)}")
        return None

def send_to_transcription_api(video_url, meeting_title="Teams Meeting"):
    """Envia a URL do vídeo para a API de transcrição."""
    try:
        payload = {
            "video_url": video_url,
            "title": meeting_title
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        response = requests.post(TRANSCRIPTION_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        logging.info(f"Transcrição iniciada com sucesso: {result}")
        return True
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro ao enviar para API de transcrição: {str(e)}")
        return False
    except Exception as e:
        logging.error(f"Exceção ao enviar para API de transcrição: {str(e)}")
        return False

def process_recording_notification(notification_data):
    """Processa uma notificação de nova gravação."""
    try:
        # Extrair informações da notificação
        resource = notification_data.get("resource", "")
        change_type = notification_data.get("changeType", "")
        
        logging.info(f"Processando notificação: {change_type} para recurso: {resource}")
        
        if change_type != "created":
            logging.info(f"Ignorando notificação do tipo: {change_type}")
            return True
        
        # Obter token de acesso
        access_token = get_graph_access_token()
        if not access_token:
            logging.error("Não foi possível obter token de acesso")
            return False
        
        # Extrair ID da gravação do recurso
        # O formato típico é: communications/callRecords/{callId}/recordings/{recordingId}
        resource_parts = resource.split("/")
        if len(resource_parts) >= 4 and "recordings" in resource_parts:
            recording_id = resource_parts[-1]
            call_id = resource_parts[-3]
            
            logging.info(f"Processando gravação ID: {recording_id} da chamada: {call_id}")
            
            # Obter URL de download
            download_url = get_recording_download_url(recording_id, access_token)
            if not download_url:
                logging.error(f"Não foi possível obter URL de download para: {recording_id}")
                return False
            
            # Enviar para API de transcrição
            success = send_to_transcription_api(download_url, f"Teams Meeting - {call_id}")
            if success:
                logging.info(f"Gravação {recording_id} enviada para transcrição com sucesso")
                return True
            else:
                logging.error(f"Falha ao enviar gravação {recording_id} para transcrição")
                return False
        else:
            logging.warning(f"Formato de recurso não reconhecido: {resource}")
            return False
            
    except Exception as e:
        logging.error(f"Exceção ao processar notificação: {str(e)}")
        return False

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("TeamsWebhook function started.")
    
    try:
        # Verificar se é uma requisição GET (validação do webhook)
        if req.method == "GET":
            validation_token = req.params.get("validationToken")
            if validation_token:
                logging.info("Validação de webhook recebida")
                return func.HttpResponse(
                    validation_token,
                    status_code=200,
                    headers={"Content-Type": "text/plain"}
                )
            else:
                return func.HttpResponse("Missing validation token", status_code=400)
        
        # Processar requisição POST (notificação)
        if req.method == "POST":
            try:
                req_body = req.get_json()
            except ValueError:
                return func.HttpResponse("Invalid JSON body", status_code=400)
            
            if not req_body:
                return func.HttpResponse("Empty request body", status_code=400)
            
            # Processar notificações
            notifications = req_body.get("value", [])
            if not notifications:
                logging.warning("Nenhuma notificação encontrada no corpo da requisição")
                return func.HttpResponse("No notifications found", status_code=400)
            
            processed_count = 0
            for notification in notifications:
                if process_recording_notification(notification):
                    processed_count += 1
            
            logging.info(f"Processadas {processed_count} de {len(notifications)} notificações")
            
            return func.HttpResponse(
                f"Processed {processed_count} notifications",
                status_code=200
            )
        
        return func.HttpResponse("Method not allowed", status_code=405)
        
    except Exception as e:
        logging.exception("Erro não tratado na função TeamsWebhook")
        return func.HttpResponse(f"Internal error: {str(e)}", status_code=500)
