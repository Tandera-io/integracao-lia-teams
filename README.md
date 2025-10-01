# Integração LIA Teams - Azure Function App

Este repositório contém uma Azure Function App para integração automática com Microsoft Teams, capturando gravações de reuniões e enviando para a API de transcrição.

## Estrutura do Projeto

- `CopyGraphToBlob/` - Função para copiar dados do Microsoft Graph para Azure Blob Storage
- `TeamsWebhook/` - **NOVA** - Função que recebe webhooks do Microsoft Graph quando gravações são criadas
- `SubscriptionManager/` - **NOVA** - Função para gerenciar subscrições de webhooks do Microsoft Graph
- `host.json` - Configurações do host da Azure Function
- `requirements.txt` - Dependências Python necessárias
- `local.settings.json` - Configurações locais (não commitado)

## Configuração

### 1. Configurar Credenciais

Copie o arquivo `local.settings.json.example` para `local.settings.json` e configure:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "sua_connection_string_aqui",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "STORAGE_ACCOUNT_NAME": "seu_storage_account",
    "MICROSOFT_CLIENT_ID": "seu_client_id_aqui",
    "MICROSOFT_CLIENT_SECRET": "seu_client_secret_aqui",
    "MICROSOFT_TENANT_ID": "seu_tenant_id_aqui",
    "TRANSCRIPTION_API_URL": "https://liacrm-transcription-api.up.railway.app/api/transcribe",
    "WEBHOOK_VALIDATION_TOKEN": "teams-watcher-webhook-secret-2024"
  }
}
```

### 2. Instalar Dependências

```bash
pip install -r requirements.txt
```

### 3. Executar Localmente

```bash
func start
```

## Como Usar

### 1. Fazer Deploy da Function App

Use o Azure CLI ou o portal do Azure para fazer o deploy da Function App.

### 2. Configurar Variáveis de Ambiente

No Azure Portal, configure as seguintes variáveis de ambiente na sua Function App:

- `MICROSOFT_CLIENT_ID`: ID do aplicativo registrado no Microsoft Entra ID
- `MICROSOFT_CLIENT_SECRET`: Segredo do cliente do aplicativo
- `MICROSOFT_TENANT_ID`: ID do tenant do Azure
- `TRANSCRIPTION_API_URL`: URL da API de transcrição
- `WEBHOOK_VALIDATION_TOKEN`: Token para validação de webhooks

### 3. Criar Subscrição de Webhook

Após o deploy, crie uma subscrição para receber notificações:

```bash
curl -X GET "https://sua-function-app.azurewebsites.net/api/SubscriptionManager?action=create&webhook_url=https://sua-function-app.azurewebsites.net/api/TeamsWebhook"
```

### 4. Gerenciar Subscrições

```bash
# Listar subscrições ativas
curl -X GET "https://sua-function-app.azurewebsites.net/api/SubscriptionManager?action=list"

# Renovar subscrição (necessário a cada hora)
curl -X GET "https://sua-function-app.azurewebsites.net/api/SubscriptionManager?action=renew&subscription_id=SEU_SUBSCRIPTION_ID"

# Deletar subscrição
curl -X GET "https://sua-function-app.azurewebsites.net/api/SubscriptionManager?action=delete&subscription_id=SEU_SUBSCRIPTION_ID"
```

## Fluxo de Funcionamento

1. **Subscrição**: O serviço se inscreve para receber notificações do Microsoft Graph quando gravações são criadas
2. **Webhook**: Quando uma reunião é gravada, o Microsoft Graph envia uma notificação para `TeamsWebhook`
3. **Processamento**: A função `TeamsWebhook` obtém a URL de download da gravação
4. **Transcrição**: A URL é enviada para a API de transcrição (`liacrm-transcription-api.up.railway.app`)

## Funções Disponíveis

### TeamsWebhook
- **URL**: `/api/TeamsWebhook`
- **Métodos**: GET (validação), POST (notificações)
- **Descrição**: Recebe webhooks do Microsoft Graph e processa gravações

### SubscriptionManager
- **URL**: `/api/SubscriptionManager`
- **Parâmetros**:
  - `action`: create, list, delete, renew
  - `webhook_url`: URL do webhook (para create)
  - `subscription_id`: ID da subscrição (para delete/renew)

### CopyGraphToBlob (Legado)
- **URL**: `/api/CopyGraphToBlob`
- **Descrição**: Copia arquivos de URLs para Azure Blob Storage

## Monitoramento

- Verifique os logs da Function App no Azure Portal
- As subscrições expiram a cada hora e precisam ser renovadas
- Configure um Azure Logic App ou Timer Function para renovação automática

## Permissões Necessárias

O aplicativo registrado no Microsoft Entra ID precisa das seguintes permissões:
- `OnlineMeetingRecording.Read.All` (Application)
- Consentimento de administrador concedido

## Troubleshooting

### Webhook não recebe notificações
1. Verifique se a subscrição está ativa
2. Confirme se a URL do webhook está acessível publicamente
3. Verifique os logs da Function App

### Erro de autenticação
1. Confirme as credenciais nas variáveis de ambiente
2. Verifique se o Client Secret não expirou
3. Confirme se as permissões foram concedidas

### API de transcrição não recebe chamadas
1. Verifique se a `TRANSCRIPTION_API_URL` está correta
2. Confirme se a API está online
3. Verifique os logs para erros de rede

## Segurança

- **NUNCA** commite credenciais no código
- Use variáveis de ambiente para todas as configurações sensíveis
- O arquivo `local.settings.json` está no `.gitignore` para evitar commit acidental de credenciais
- Renove o Client Secret periodicamente conforme políticas de segurança
