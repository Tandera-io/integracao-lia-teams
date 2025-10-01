# Teams Watcher Service - FastAPI

Serviço de integração automática com Microsoft Teams para captura de gravações de reuniões e envio para API de transcrição.

## 🚀 Arquitetura

- **FastAPI**: Framework web moderno e rápido
- **Microsoft Graph**: Integração com Teams para receber notificações de gravações
- **Webhooks**: Recebimento automático de notificações quando gravações são criadas
- **Railway**: Plataforma de deploy com controle total

## 📁 Estrutura do Projeto

```
├── main.py                 # Aplicação FastAPI principal
├── requirements.txt        # Dependências Python
├── Procfile               # Comando de inicialização para Railway
├── runtime.txt            # Versão do Python
├── README.md              # Documentação
└── legacy/                # Código original Azure Functions (para referência)
    ├── CopyGraphToBlob/
    ├── TeamsWebhook/
    └── SubscriptionManager/
```

## ⚙️ Configuração

### 1. Variáveis de Ambiente

Configure as seguintes variáveis no Railway:

```bash
MICROSOFT_CLIENT_ID=a4796fb5-ecd7-4002-a8e7-93416ad0c1b1
MICROSOFT_CLIENT_SECRET=seu_client_secret_aqui
MICROSOFT_TENANT_ID=78481405-a361-415a-b544-49e3018b711d
TRANSCRIPTION_API_URL=https://liacrm-transcription-api.up.railway.app/api/transcribe
WEBHOOK_VALIDATION_TOKEN=teams-watcher-webhook-secret-2024
PORT=8000
```

### 2. Deploy no Railway

1. Conecte o repositório GitHub ao Railway
2. Configure as variáveis de ambiente
3. O deploy será automático

## 🔗 Endpoints da API

### Informações Gerais
- `GET /` - Informações sobre o serviço
- `GET /health` - Health check

### Webhook do Teams
- `GET /api/TeamsWebhook?validationToken=TOKEN` - Validação do webhook
- `POST /api/TeamsWebhook` - Recebe notificações de gravações

### Gerenciamento de Subscrições
- `GET /api/SubscriptionManager?action=list` - Lista subscrições ativas
- `GET /api/SubscriptionManager?action=create&webhook_url=URL` - Cria nova subscrição
- `GET /api/SubscriptionManager?action=renew&subscription_id=ID` - Renova subscrição
- `GET /api/SubscriptionManager?action=delete&subscription_id=ID` - Deleta subscrição

## 🎯 Como Usar

### 1. Após o Deploy

Sua aplicação estará disponível em: `https://seu-app.up.railway.app`

### 2. Criar Subscrição

```bash
curl -X GET "https://seu-app.up.railway.app/api/SubscriptionManager?action=create&webhook_url=https://seu-app.up.railway.app/api/TeamsWebhook"
```

### 3. Verificar Subscrições

```bash
curl -X GET "https://seu-app.up.railway.app/api/SubscriptionManager?action=list"
```

### 4. Renovar Subscrição (a cada 50 minutos)

```bash
curl -X GET "https://seu-app.up.railway.app/api/SubscriptionManager?action=renew&subscription_id=SEU_SUBSCRIPTION_ID"
```

## 🔄 Fluxo de Funcionamento

1. **Subscrição Ativa**: Serviço se inscreve para receber notificações do Microsoft Graph
2. **Reunião Gravada**: Teams grava uma reunião automaticamente
3. **Webhook Recebido**: Microsoft Graph envia notificação para `/api/TeamsWebhook`
4. **Processamento**: Serviço obtém URL de download da gravação via Graph API
5. **Transcrição**: URL é enviada para `liacrm-transcription-api.up.railway.app`
6. **Resultado**: Transcrição é processada automaticamente

## 🛠️ Desenvolvimento Local

```bash
# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
export MICROSOFT_CLIENT_ID="seu_client_id"
export MICROSOFT_CLIENT_SECRET="seu_client_secret"
export MICROSOFT_TENANT_ID="seu_tenant_id"
export TRANSCRIPTION_API_URL="https://liacrm-transcription-api.up.railway.app/api/transcribe"

# Executar aplicação
uvicorn main:app --reload --port 8000
```

Acesse: `http://localhost:8000`

## 📊 Monitoramento

- **Logs**: Disponíveis no painel do Railway
- **Health Check**: `GET /health`
- **Métricas**: Painel do Railway mostra CPU, memória e requests

## 🔒 Segurança

- ✅ Todas as credenciais via variáveis de ambiente
- ✅ Nenhuma credencial hardcoded no código
- ✅ Validação de webhooks do Microsoft Graph
- ✅ Logs detalhados para auditoria

## 🆘 Troubleshooting

### Webhook não recebe notificações
1. Verifique se a subscrição está ativa: `GET /api/SubscriptionManager?action=list`
2. Confirme se a URL está acessível publicamente
3. Verifique os logs no Railway

### Erro de autenticação
1. Confirme as variáveis de ambiente no Railway
2. Verifique se o Client Secret não expirou
3. Confirme se as permissões foram concedidas no Azure

### API de transcrição não recebe chamadas
1. Verifique se `TRANSCRIPTION_API_URL` está correta
2. Confirme se a API está online
3. Verifique os logs para erros de rede

## 🔄 Migração do Azure Functions

Este projeto foi migrado de Azure Functions para FastAPI mantendo:
- ✅ **Mesma funcionalidade** de webhook
- ✅ **Mesma integração** com Microsoft Graph  
- ✅ **Mesmo envio** para transcription-api
- ✅ **Mesmas credenciais** e configurações
- ✅ **Mesma lógica** de negócio

**Vantagens da migração:**
- 🚀 Deploy mais simples no Railway
- 📊 Melhor controle e monitoramento
- 🔧 Mais flexibilidade para customizações
- 💰 Potencial redução de custos

## 📞 Suporte

Para dúvidas ou problemas:
1. Verifique os logs no Railway
2. Consulte a documentação da Microsoft Graph
3. Teste os endpoints individualmente
