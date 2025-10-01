import logging
import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
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
WEBHOOK_VALIDATION_TOKEN = os.environ.get("WEBHOOK_VALIDATION_TOKEN")

# Scopes necessários para o Microsoft Graph
SCOPES = ["https://graph.microsoft.com/.default"]

# Inicializar FastAPI
app = FastAPI(
    title="Teams Watcher Service",
    description="Serviço de integração automática com Microsoft Teams para captura de gravações",
    version="1.0.0"
)

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
            logger.error(f"Erro ao obter token: {result.get('error_description', 'Erro desconhecido')}")
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
        logger.error(f"Erro ao obter URL de download: {str(e)}")
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
        
        response = requests.post(TRANSCRIPTION_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"Transcrição iniciada com sucesso: {result}")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao enviar para API de transcrição: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Exceção ao enviar para API de transcrição: {str(e)}")
        return False

def process_recording_notification(notification_data: Dict[str, Any]) -> bool:
    """Processa uma notificação de nova gravação."""
    try:
        # Extrair informações da notificação
        resource = notification_data.get("resource", "")
        change_type = notification_data.get("changeType", "")
        
        logger.info(f"Processando notificação: {change_type} para recurso: {resource}")
        
        if change_type != "created":
            logger.info(f"Ignorando notificação do tipo: {change_type}")
            return True
        
        # Obter token de acesso
        access_token = get_graph_access_token()
        if not access_token:
            logger.error("Não foi possível obter token de acesso")
            return False
        
        # Extrair ID da gravação do recurso
        # O formato típico é: communications/callRecords/{callId}/recordings/{recordingId}
        resource_parts = resource.split("/")
        if len(resource_parts) >= 4 and "recordings" in resource_parts:
            recording_id = resource_parts[-1]
            call_id = resource_parts[-3]
            
            logger.info(f"Processando gravação ID: {recording_id} da chamada: {call_id}")
            
            # Obter URL de download
            download_url = get_recording_download_url(recording_id, access_token)
            if not download_url:
                logger.error(f"Não foi possível obter URL de download para: {recording_id}")
                return False
            
            # Enviar para API de transcrição
            success = send_to_transcription_api(download_url, f"Teams Meeting - {call_id}")
            if success:
                logger.info(f"Gravação {recording_id} enviada para transcrição com sucesso")
                return True
            else:
                logger.error(f"Falha ao enviar gravação {recording_id} para transcrição")
                return False
        else:
            logger.warning(f"Formato de recurso não reconhecido: {resource}")
            return False
            
    except Exception as e:
        logger.error(f"Exceção ao processar notificação: {str(e)}")
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
