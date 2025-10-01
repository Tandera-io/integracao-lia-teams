import logging
import os
import json
from datetime import datetime, timedelta
import azure.functions as func
import requests
from msal import ConfidentialClientApplication

# Configurações do Microsoft Graph
CLIENT_ID = os.environ.get("MICROSOFT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("MICROSOFT_CLIENT_SECRET")
TENANT_ID = os.environ.get("MICROSOFT_TENANT_ID")

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

def create_subscription(webhook_url, access_token):
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
        logging.info(f"Subscrição criada com sucesso: {result.get('id')}")
        return result
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro ao criar subscrição: {str(e)}")
        if hasattr(e, 'response') and e.response:
            logging.error(f"Resposta do erro: {e.response.text}")
        return None
    except Exception as e:
        logging.error(f"Exceção ao criar subscrição: {str(e)}")
        return None

def list_subscriptions(access_token):
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
        
        logging.info(f"Encontradas {len(subscriptions)} subscrições")
        return subscriptions
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro ao listar subscrições: {str(e)}")
        return []
    except Exception as e:
        logging.error(f"Exceção ao listar subscrições: {str(e)}")
        return []

def delete_subscription(subscription_id, access_token):
    """Deleta uma subscrição específica."""
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        url = f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}"
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
        
        logging.info(f"Subscrição {subscription_id} deletada com sucesso")
        return True
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro ao deletar subscrição {subscription_id}: {str(e)}")
        return False
    except Exception as e:
        logging.error(f"Exceção ao deletar subscrição {subscription_id}: {str(e)}")
        return False

def renew_subscription(subscription_id, access_token):
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
        logging.info(f"Subscrição {subscription_id} renovada até {expiration_iso}")
        return result
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro ao renovar subscrição {subscription_id}: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Exceção ao renovar subscrição {subscription_id}: {str(e)}")
        return None

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("SubscriptionManager function started.")
    
    try:
        # Obter token de acesso
        access_token = get_graph_access_token()
        if not access_token:
            return func.HttpResponse("Erro ao obter token de acesso", status_code=500)
        
        # Determinar ação baseada nos parâmetros
        action = req.params.get("action", "list")
        
        if action == "create":
            webhook_url = req.params.get("webhook_url")
            if not webhook_url:
                return func.HttpResponse("webhook_url é obrigatório para criar subscrição", status_code=400)
            
            result = create_subscription(webhook_url, access_token)
            if result:
                return func.HttpResponse(
                    json.dumps(result, indent=2),
                    status_code=200,
                    headers={"Content-Type": "application/json"}
                )
            else:
                return func.HttpResponse("Erro ao criar subscrição", status_code=500)
        
        elif action == "list":
            subscriptions = list_subscriptions(access_token)
            return func.HttpResponse(
                json.dumps({"subscriptions": subscriptions}, indent=2),
                status_code=200,
                headers={"Content-Type": "application/json"}
            )
        
        elif action == "delete":
            subscription_id = req.params.get("subscription_id")
            if not subscription_id:
                return func.HttpResponse("subscription_id é obrigatório para deletar", status_code=400)
            
            success = delete_subscription(subscription_id, access_token)
            if success:
                return func.HttpResponse(f"Subscrição {subscription_id} deletada", status_code=200)
            else:
                return func.HttpResponse("Erro ao deletar subscrição", status_code=500)
        
        elif action == "renew":
            subscription_id = req.params.get("subscription_id")
            if not subscription_id:
                return func.HttpResponse("subscription_id é obrigatório para renovar", status_code=400)
            
            result = renew_subscription(subscription_id, access_token)
            if result:
                return func.HttpResponse(
                    json.dumps(result, indent=2),
                    status_code=200,
                    headers={"Content-Type": "application/json"}
                )
            else:
                return func.HttpResponse("Erro ao renovar subscrição", status_code=500)
        
        else:
            return func.HttpResponse(
                "Ação não reconhecida. Use: create, list, delete, ou renew",
                status_code=400
            )
    
    except Exception as e:
        logging.exception("Erro não tratado na função SubscriptionManager")
        return func.HttpResponse(f"Internal error: {str(e)}", status_code=500)
