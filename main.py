import logging
import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from uuid import uuid4

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse, JSONResponse
import requests
from msal import ConfidentialClientApplication

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurações do Microsoft Graph
CLIENT_ID = os.environ.get("MICROSOFT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("MICROSOFT_CLIENT_SECRET")
TENANT_ID = os.environ.get("MICROSOFT_TENANT_ID")
TRANSCRIPTION_API_URL = os.environ.get("TRANSCRIPTION_API_URL")
TRANSCRIPTION_API_KEY = os.environ.get("TRANSCRIPTION_API_KEY")
WEBHOOK_VALIDATION_TOKEN = os.environ.get("WEBHOOK_VALIDATION_TOKEN")

# Scopes necessários para o Microsoft Graph
SCOPES = ["https://graph.microsoft.com/.default"]

# Inicializar FastAPI
app = FastAPI(
    title="Teams Watcher Service",
    description="Serviço de integração automática com Microsoft Teams para captura de gravações",
    version="1.0.0"
)


def _format_extra(extra: Optional[Dict[str, Any]]) -> str:
    if not extra:
        return ""
    try:
        return f" | extra={json.dumps(extra, ensure_ascii=True)}"
    except (TypeError, ValueError):
        return ""


def log_http_error(response: requests.Response, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    details = {
        "status": response.status_code,
        "reason": response.reason,
        "body": response.text[:1000],
    }
    if extra:
        details.update(extra)
    logger.error(f"{message} | details={json.dumps(details, ensure_ascii=True)}")


def get_graph_access_token():
    """Obtém um token de acesso para o Microsoft Graph usando credenciais de aplicativo."""
    try:
        app_client = ConfidentialClientApplication(
            CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{TENANT_ID}",
            client_credential=CLIENT_SECRET,
        )
        
        result = app_client.acquire_token_silent(SCOPES, account=None)
        if not result:
            result = app_client.acquire_token_for_client(scopes=SCOPES)
        
        if "access_token" in result:
            return result["access_token"]
        else:
            logger.error(
                "Erro ao obter token do Graph",
                extra={"error": result.get("error"), "description": result.get("error_description")}
            )
            return None
    except Exception as e:
        logger.error(f"Exceção ao obter token: {str(e)}")
        return None

def get_recording_download_url(recording_id: str, access_token: str) -> Optional[str]:
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
        
        logger.warning(f"URL de download não encontrada para recording_id: {recording_id}")
        return None
        
    except requests.exceptions.RequestException as e:
        if e.response is not None:
            log_http_error(e.response, "Erro ao obter URL de download do Graph", {"recording_id": recording_id})
        else:
            logger.error(
                "Erro ao obter URL de download do Graph sem resposta",
                extra={"recording_id": recording_id, "error": str(e)}
            )
        return None
    except Exception as e:
        logger.error(f"Exceção ao obter URL de download: {str(e)}")
        return None

def send_to_transcription_api(video_url: str, meeting_title: str = "Teams Meeting") -> bool:
    """Envia a URL do vídeo para a API de transcrição."""
    try:
        payload = {
            "video_url": video_url,
            "title": meeting_title
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if TRANSCRIPTION_API_KEY:
            headers["X-Api-Key"] = TRANSCRIPTION_API_KEY
        
        response = requests.post(TRANSCRIPTION_API_URL, json=payload, headers=headers)
        response.raise_for_status()

        logger.info(
            "Transcrição iniciada com sucesso",
            extra={"status": response.status_code, "title": meeting_title}
        )
        return True
        
    except requests.exceptions.RequestException as e:
        if hasattr(e, "response") and e.response is not None:
            log_http_error(
                e.response,
                "Erro ao enviar para API de transcrição",
                {"title": meeting_title, "video_url": video_url}
            )
        else:
            logger.error(
                "Erro ao enviar para API de transcrição sem resposta",
                extra={"title": meeting_title, "video_url": video_url, "error": str(e)}
            )
        return False
    except Exception as e:
        logger.error(f"Exceção ao enviar para API de transcrição: {str(e)}")
        return False

def process_recording_notification(notification_data: Dict[str, Any]) -> bool:
    """Processa uma notificação de nova gravação."""
    correlation_id = str(uuid4())
    try:
        # Extrair informações da notificação
        resource = notification_data.get("resource", "")
        change_type = notification_data.get("changeType", "")
        
        logger.info(
            "Processando notificação",
            extra={"correlation_id": correlation_id, "change_type": change_type, "resource": resource}
        )
        
        if change_type != "created":
            logger.info(
                "Ignorando notificação",
                extra={"correlation_id": correlation_id, "motivo": "changeType diferente", "change_type": change_type}
            )
            return True
        
        # Obter token de acesso
        access_token = get_graph_access_token()
        if not access_token:
            logger.error("Não foi possível obter token de acesso", extra={"correlation_id": correlation_id})
            return False
        
        # Extrair ID da gravação do recurso
        # O formato típico é: communications/callRecords/{callId}/recordings/{recordingId}
        resource_parts = resource.split("/")
        if len(resource_parts) >= 4 and "recordings" in resource_parts:
            recording_id = resource_parts[-1]
            call_id = resource_parts[-3]
            
            context = {
                "correlation_id": correlation_id,
                "recording_id": recording_id,
                "call_id": call_id,
            }
            logger.info("Buscando URL de download", extra=context)
            
            # Obter URL de download
            download_url = get_recording_download_url(recording_id, access_token)
            if not download_url:
                logger.error("Não foi possível obter URL de download", extra=context)
                return False
            
            # Enviar para API de transcrição
            success = send_to_transcription_api(download_url, f"Teams Meeting - {call_id}")
            if success:
                logger.info("Gravação enviada para transcrição com sucesso", extra=context)
                return True
            else:
                logger.error("Falha ao enviar gravação para transcrição", extra=context)
                return False
        else:
            logger.warning(
                "Formato de recurso não reconhecido",
                extra={"correlation_id": correlation_id, "resource": resource}
            )
            return False
            
    except Exception as e:
        logger.error(
            "Exceção ao processar notificação",
            extra={"correlation_id": correlation_id, "error": str(e)}
        )
        return False

# Funções para gerenciamento de subscrições
def create_subscription(webhook_url: str, access_token: str) -> Optional[Dict[str, Any]]:
    """Cria uma nova subscrição para gravações de reuniões."""
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Data de expiração (máximo 1 hora para este tipo de recurso)
        expiration_time = datetime.utcnow() + timedelta(minutes=55)
        expiration_iso = expiration_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        
        subscription_data = {
            "changeType": "created",
            "notificationUrl": webhook_url,
            "resource": "communications/onlineMeetings/getAllRecordings",
            "expirationDateTime": expiration_iso,
            "clientState": "teams-watcher-subscription"
        }
        
        url = "https://graph.microsoft.com/v1.0/subscriptions"
        response = requests.post(url, headers=headers, json=subscription_data)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"Subscrição criada com sucesso: {result.get('id')}")
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao criar subscrição: {str(e)}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"Resposta do erro: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Exceção ao criar subscrição: {str(e)}")
        return None

def list_subscriptions(access_token: str) -> list:
    """Lista todas as subscrições ativas."""
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        url = "https://graph.microsoft.com/v1.0/subscriptions"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        subscriptions = result.get("value", [])
        
        logger.info(f"Encontradas {len(subscriptions)} subscrições")
        return subscriptions
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao listar subscrições: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"Exceção ao listar subscrições: {str(e)}")
        return []

def delete_subscription(subscription_id: str, access_token: str) -> bool:
    """Deleta uma subscrição específica."""
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        url = f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}"
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
        
        logger.info(f"Subscrição {subscription_id} deletada com sucesso")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao deletar subscrição {subscription_id}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Exceção ao deletar subscrição {subscription_id}: {str(e)}")
        return False

def renew_subscription(subscription_id: str, access_token: str) -> Optional[Dict[str, Any]]:
    """Renova uma subscrição existente."""
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Nova data de expiração (55 minutos a partir de agora)
        expiration_time = datetime.utcnow() + timedelta(minutes=55)
        expiration_iso = expiration_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        
        update_data = {
            "expirationDateTime": expiration_iso
        }
        
        url = f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}"
        response = requests.patch(url, headers=headers, json=update_data)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"Subscrição {subscription_id} renovada até {expiration_iso}")
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao renovar subscrição {subscription_id}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Exceção ao renovar subscrição {subscription_id}: {str(e)}")
        return None

# Endpoints da API

@app.get("/")
async def root():
    """Endpoint raiz com informações sobre o serviço."""
    return {
        "service": "Teams Watcher Service",
        "version": "1.0.0",
        "description": "Serviço de integração automática com Microsoft Teams",
        "endpoints": {
            "webhook": "/api/TeamsWebhook",
            "subscription_manager": "/api/SubscriptionManager",
            "health": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """Endpoint de health check."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/TeamsWebhook")
async def teams_webhook_get(validationToken: Optional[str] = Query(None)):
    """Validação do webhook do Microsoft Graph."""
    logger.info(f"Validação de webhook recebida com token: {validationToken}")
    if validationToken:
        logger.info(f"Retornando token de validação: {validationToken}")
        return PlainTextResponse(content=validationToken, status_code=200)
    else:
        logger.error("Token de validação não fornecido")
        raise HTTPException(status_code=400, detail="Missing validation token")

@app.post("/api/TeamsWebhook")
async def teams_webhook_post(request: Request):
    """Recebe notificações do Microsoft Graph sobre gravações."""
    logger.info("TeamsWebhook POST recebido")
    
    try:
        req_body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    if not req_body:
        raise HTTPException(status_code=400, detail="Empty request body")
    
    # Processar notificações
    notifications = req_body.get("value", [])
    if not notifications:
        logger.warning("Nenhuma notificação encontrada no corpo da requisição")
        raise HTTPException(status_code=400, detail="No notifications found")
    
    processed_count = 0
    for notification in notifications:
        if process_recording_notification(notification):
            processed_count += 1
    
    logger.info(f"Processadas {processed_count} de {len(notifications)} notificações")
    
    return {"message": f"Processed {processed_count} notifications"}

@app.get("/api/SubscriptionManager")
async def subscription_manager(
    action: str = Query("list"),
    webhook_url: Optional[str] = Query(None),
    subscription_id: Optional[str] = Query(None)
):
    """Gerencia subscrições de webhook do Microsoft Graph."""
    logger.info(f"SubscriptionManager chamado com ação: {action}")
    
    # Obter token de acesso
    access_token = get_graph_access_token()
    if not access_token:
        raise HTTPException(status_code=500, detail="Erro ao obter token de acesso")
    
    if action == "create":
        if not webhook_url:
            raise HTTPException(status_code=400, detail="webhook_url é obrigatório para criar subscrição")
        
        result = create_subscription(webhook_url, access_token)
        if result:
            return result
        else:
            raise HTTPException(status_code=500, detail="Erro ao criar subscrição")
    
    elif action == "list":
        subscriptions = list_subscriptions(access_token)
        return {"subscriptions": subscriptions}
    
    elif action == "delete":
        if not subscription_id:
            raise HTTPException(status_code=400, detail="subscription_id é obrigatório para deletar")
        
        success = delete_subscription(subscription_id, access_token)
        if success:
            return {"message": f"Subscrição {subscription_id} deletada"}
        else:
            raise HTTPException(status_code=500, detail="Erro ao deletar subscrição")
    
    elif action == "renew":
        if not subscription_id:
            raise HTTPException(status_code=400, detail="subscription_id é obrigatório para renovar")
        
        result = renew_subscription(subscription_id, access_token)
        if result:
            return result
        else:
            raise HTTPException(status_code=500, detail="Erro ao renovar subscrição")
    
    else:
        raise HTTPException(
            status_code=400, 
            detail="Ação não reconhecida. Use: create, list, delete, ou renew"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
