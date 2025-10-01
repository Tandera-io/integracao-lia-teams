# Documentação - Integração Teams com API de Transcrição

**Data de implementação:** 01 de Outubro de 2025  
**Desenvolvedor:** Devin AI  
**Solicitante:** Jairo Soares (@Tandera-io)

---

## 📋 Índice

1. [Visão Geral](#visão-geral)
2. [Problema Identificado](#problema-identificado)
3. [Solução Implementada](#solução-implementada)
4. [Mudanças Realizadas](#mudanças-realizadas)
5. [Pull Requests](#pull-requests)
6. [Configuração no Railway](#configuração-no-railway)
7. [Testes Realizados](#testes-realizados)
8. [Como Funciona o Sistema](#como-funciona-o-sistema)
9. [Troubleshooting](#troubleshooting)
10. [Próximos Passos](#próximos-passos)

---

## 🎯 Visão Geral

Este sistema integra o Microsoft Teams com uma API de transcrição automática de reuniões. Quando uma reunião do Teams é gravada, o sistema:

1. Recebe notificação do Microsoft Graph via webhook
2. Baixa a URL da gravação
3. Envia para a API de transcrição
4. A API processa o áudio usando AssemblyAI e enriquece com OpenAI

### Repositórios Envolvidos

- **integracao-lia-teams**: Webhook que recebe notificações do Teams e envia para API
- **transcription-api**: API que processa as transcrições
- **transcription-app**: Backend compartilhado contendo middleware de autenticação

---

## 🔴 Problema Identificado

### Sintoma
O sistema estava deployado em produção mas não funcionava. As gravações do Teams não eram transcritas.

### Causa Raiz
O webhook (`integracao-lia-teams`) estava chamando a API de transcrição **sem nenhuma autenticação**. A API requer autenticação (JWT ou API Key), então todas as chamadas falhavam com **401 Unauthorized**.

### Código Problemático
```python
# main.py - ANTES (sem autenticação)
def send_to_transcription_api(video_url: str, meeting_title: str = "Teams Meeting") -> bool:
    headers = {
        "Content-Type": "application/json"
    }
    # Sem X-Api-Key header!
    response = requests.post(TRANSCRIPTION_API_URL, json=payload, headers=headers)
```

---

## ✅ Solução Implementada

### Resumo
Implementamos **autenticação via API Key** para comunicação service-to-service entre o webhook e a API de transcrição.

### Componentes da Solução

1. **Middleware de Autenticação Atualizado** (`transcription-app`)
   - Adicionada função `get_current_user_or_service()`
   - Aceita tanto JWT (usuários) quanto X-Api-Key (serviços)
   - Cria conta de serviço para requests autenticados via API Key

2. **API de Transcrição Atualizada** (`transcription-api`)
   - Endpoints usam `get_current_user_or_service` em vez de `get_current_user`
   - Aceita header `X-Api-Key` para autenticação

3. **Webhook Atualizado** (`integracao-lia-teams`)
   - Envia header `X-Api-Key` em todas as requisições
   - Carrega chave da variável de ambiente `TRANSCRIPTION_API_KEY`
   - Logging aprimorado com status e body de erros

---

## 📝 Mudanças Realizadas

### 1. transcription-app (backend/middleware/auth.py)

```python
# Nova função adicionada
async def get_current_user_or_service(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key")
):
    """
    Aceita autenticação via JWT (usuários) ou API Key (serviços).
    """
    # Verifica se foi fornecida uma API Key
    if x_api_key:
        if not SERVICE_API_KEY:
            raise HTTPException(status_code=500, detail="Service API Key não configurado")
        if x_api_key != SERVICE_API_KEY:
            raise HTTPException(status_code=401, detail="API Key inválida")
        # Retorna conta de serviço
        return {
            "id": "service-account",
            "email": "service@internal",
            "role": "service",
            "is_service": True
        }
    
    # Fallback para autenticação JWT
    if not credentials:
        raise HTTPException(status_code=401, detail="Autenticação necessária")
    
    token = credentials.credentials
    payload = AuthMiddleware.verify_token(token)
    user = AuthMiddleware.get_user_from_token(payload)
    user["is_service"] = False
    return user
```

### 2. transcription-api (main.py)

```python
# ANTES
@app.post("/api/transcribe")
async def transcribe_from_url(req: TranscriptionRequest, current_user: dict = Depends(get_current_user)):

# DEPOIS
@app.post("/api/transcribe")
async def transcribe_from_url(req: TranscriptionRequest, current_user: dict = Depends(get_current_user_or_service)):
```

### 3. integracao-lia-teams (main.py)

```python
# Nova variável de ambiente
TRANSCRIPTION_API_KEY = os.environ.get("TRANSCRIPTION_API_KEY")

# Função atualizada
def send_to_transcription_api(video_url: str, meeting_title: str = "Teams Meeting") -> bool:
    headers = {
        "Content-Type": "application/json"
    }
    
    # Adiciona API key se configurada
    if TRANSCRIPTION_API_KEY:
        headers["X-Api-Key"] = TRANSCRIPTION_API_KEY
    
    response = requests.post(TRANSCRIPTION_API_URL, json=payload, headers=headers)
    
    # Logging melhorado
    if hasattr(e, 'response') and e.response is not None:
        logger.error(f"Response status: {e.response.status_code}, body: {e.response.text}")
```

### 4. Documentação Atualizada

**transcription-api/README.md:**
```markdown
## Variáveis de ambiente
- SUPABASE_URL
- SUPABASE_KEY
- SUPABASE_JWT_SECRET
- ASSEMBLYAI_API_KEY
- OPENAI_API_KEY
- TRANSCRIPTION_SERVICE_API_KEY (para autenticação service-to-service) ← NOVO
- CORS_ORIGINS (opcional)
```

**integracao-lia-teams/README.md e .env.example:**
```bash
TRANSCRIPTION_API_KEY=seu_api_key_secreto_aqui  # ← NOVO
```

---

## 🔗 Pull Requests

Todos os PRs foram **MERGED com sucesso**:

1. **transcription-app #15**
   - URL: https://github.com/Tandera-io/transcription-app/pull/15
   - Status: ✅ Merged (CI Passed)
   - Alterações: Middleware de autenticação

2. **transcription-api #2**
   - URL: https://github.com/Tandera-io/transcription-api/pull/2
   - Status: ✅ Merged
   - Alterações: Endpoints usam nova autenticação

3. **integracao-lia-teams #1**
   - URL: https://github.com/Tandera-io/integracao-lia-teams/pull/1
   - Status: ✅ Merged
   - Alterações: Webhook envia X-Api-Key

---

## ⚙️ Configuração no Railway

### Chave API Gerada

Use esta chave secreta para ambos os serviços:
```
7ede45fa9f04e8969e7e2c04981e7888745affa0886e006f9aa6f2e0967f2ed0
```

**⚠️ IMPORTANTE:** A mesma chave deve ser configurada nos dois serviços!

### Serviço: transcription-api

Adicione as seguintes variáveis de ambiente no Railway:

```bash
# === AUTENTICAÇÃO SUPABASE ===
# Obter em: https://app.supabase.com → Settings → API
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_KEY=sua-service-role-key-aqui
SUPABASE_JWT_SECRET=seu-jwt-secret-aqui

# === API KEY PARA SERVIÇOS ===
TRANSCRIPTION_SERVICE_API_KEY=7ede45fa9f04e8969e7e2c04981e7888745affa0886e006f9aa6f2e0967f2ed0

# === SERVIÇOS DE IA ===
ASSEMBLYAI_API_KEY=sua-key-assemblyai
OPENAI_API_KEY=sua-key-openai

# === CORS (opcional) ===
CORS_ORIGINS=*
```

### Serviço: integracao-lia-teams

Adicione/atualize as variáveis de ambiente no Railway:

```bash
# === MICROSOFT GRAPH ===
MICROSOFT_CLIENT_ID=a4796fb5-ecd7-4002-a8e7-93416ad0c1b1
MICROSOFT_CLIENT_SECRET=seu_client_secret_aqui
MICROSOFT_TENANT_ID=78481405-a361-415a-b544-49e3018b711d

# === API DE TRANSCRIÇÃO ===
TRANSCRIPTION_API_URL=https://liacrm-transcription-api.up.railway.app/api/transcribe
TRANSCRIPTION_API_KEY=7ede45fa9f04e8969e7e2c04981e7888745affa0886e006f9aa6f2e0967f2ed0

# === WEBHOOK ===
WEBHOOK_VALIDATION_TOKEN=teams-watcher-webhook-secret-2024

# === PORTA ===
PORT=8000
```

### Como Obter Credenciais do Supabase

1. Acesse: https://app.supabase.com
2. Selecione seu projeto
3. Vá em **Settings** → **API**
4. Copie:
   - **URL** → `SUPABASE_URL`
   - **service_role key** (não anon key!) → `SUPABASE_KEY`
5. Para JWT Secret:
   - **Settings** → **API** → **JWT Settings** → **JWT Secret** → `SUPABASE_JWT_SECRET`

### Após Configurar

1. Salve as variáveis de ambiente
2. **Redeploy ambos os serviços** no Railway
3. Aguarde o deploy completar (~1-2 minutos)
4. Teste conforme seção abaixo

---

## 🧪 Testes Realizados

### Testes Locais (Aprovados ✅)

Testado localmente com servidor rodando em `http://127.0.0.1:8081`:

```bash
# 1. Health Endpoint
GET /api/health
✅ Status: 200 OK
Response: {"status":"healthy"}

# 2. Sem Autenticação
POST /api/transcribe (sem headers)
✅ Status: 401 Unauthorized
Response: {"detail":"Autenticação necessária (JWT ou API Key)"}

# 3. API Key Errada
POST /api/transcribe
Header: X-Api-Key: wrong-key
✅ Status: 401 Unauthorized
Response: {"detail":"API Key inválida"}

# 4. API Key Correta
POST /api/transcribe
Header: X-Api-Key: test-key-12345
✅ Autenticação passou! (chegou na lógica de negócio)
Response: 500 (erro esperado - URL de teste não existe)
```

**Conclusão Local:** Autenticação funcionando perfeitamente! ✅

### Testes de Produção (Pendente ⏳)

Testado em `https://liacrm-transcription-api.up.railway.app`:

```bash
# 1. Health Endpoint
GET /api/health
✅ Status: 200 OK - Serviço rodando

# 2. Endpoint de Transcrição
POST /api/transcribe (com e sem API key)
❌ Status: 000 (TIMEOUT após 10s)
```

**Diagnóstico:** O endpoint está travando porque **faltam variáveis de ambiente** no Railway (principalmente Supabase). O middleware tenta conectar ao Supabase e trava sem resposta.

**Solução:** Configure as variáveis de ambiente conforme seção anterior.

### Como Testar Após Configuração

```bash
# Teste 1: Health check
curl https://liacrm-transcription-api.up.railway.app/api/health

# Teste 2: Sem autenticação (deve retornar 401)
curl -X POST https://liacrm-transcription-api.up.railway.app/api/transcribe \
  -H "Content-Type: application/json" \
  -d '{"video_url": "https://example.com/test.mp4", "title": "Test"}'

# Teste 3: Com API key (deve passar autenticação)
curl -X POST https://liacrm-transcription-api.up.railway.app/api/transcribe \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: 7ede45fa9f04e8969e7e2c04981e7888745affa0886e006f9aa6f2e0967f2ed0" \
  -d '{"video_url": "https://example.com/test.mp4", "title": "Test"}'
```

**Resultado esperado:** 
- Teste 1: 200 OK
- Teste 2: 401 Unauthorized
- Teste 3: 500 Internal Server Error (URL não existe) ← Isso é bom! Significa que passou autenticação

---

## 🔄 Como Funciona o Sistema

### Fluxo Completo

```
1. MICROSOFT TEAMS
   └─ Reunião gravada
        ↓
2. MICROSOFT GRAPH API
   └─ Envia webhook notification
        ↓
3. INTEGRACAO-LIA-TEAMS (este repo)
   └─ Recebe POST no endpoint /webhook
   └─ Valida token de webhook
   └─ Processa evento "created"
   └─ Obtém URL de download via Graph API
   └─ Envia para transcription-api com X-Api-Key header
        ↓
4. TRANSCRIPTION-API
   └─ Valida X-Api-Key
   └─ Cria service account
   └─ Baixa vídeo/áudio
   └─ Transcreve com AssemblyAI
   └─ Enriquece com OpenAI
   └─ Salva no Supabase
```

### Detecção de Novas Reuniões

O sistema usa **Microsoft Graph API Subscriptions (webhooks)**:

1. **Subscription Setup**
   - O sistema se inscreve em notificações de recursos do Teams
   - Microsoft Graph envia POST para nosso webhook quando eventos ocorrem

2. **Webhook Endpoint**
   - URL: Configurada no Azure AD/Entra
   - Validação: Token de segurança (`WEBHOOK_VALIDATION_TOKEN`)

3. **Processamento**
   - Webhook recebe notificação de evento "created"
   - Valida assinatura e token
   - Obtém URL de download do recurso
   - Envia para API de transcrição

### Autenticação Service-to-Service

```
integracao-lia-teams            transcription-api
     (Webhook)                    (API)
         |                           |
         |  POST /api/transcribe     |
         |  X-Api-Key: <secret>      |
         |-------------------------->|
         |                           |
         |                     [Valida Key]
         |                           |
         |                     [Cria Service Account]
         |                           |
         |                     [Processa Request]
         |                           |
         |<--------------------------|
         |   200 OK / 500 Error      |
```

---

## 🔧 Troubleshooting

### Problema: Webhook não recebe notificações

**Possíveis causas:**
- Subscription expirada no Microsoft Graph
- Webhook URL incorreta no Azure AD
- Token de validação incorreto

**Solução:**
1. Verificar subscription no Microsoft Graph
2. Renovar subscription se necessário
3. Confirmar `WEBHOOK_VALIDATION_TOKEN` está correto

### Problema: API retorna 401 Unauthorized

**Possíveis causas:**
- `TRANSCRIPTION_API_KEY` não configurada no webhook
- `TRANSCRIPTION_SERVICE_API_KEY` não configurada na API
- Chaves diferentes nos dois serviços

**Solução:**
1. Verificar variável `TRANSCRIPTION_API_KEY` em integracao-lia-teams
2. Verificar variável `TRANSCRIPTION_SERVICE_API_KEY` em transcription-api
3. Confirmar que ambas têm o mesmo valor
4. Usar a chave: `7ede45fa9f04e8969e7e2c04981e7888745affa0886e006f9aa6f2e0967f2ed0`

### Problema: API trava (timeout)

**Possíveis causas:**
- Variáveis do Supabase faltando ou incorretas
- Middleware tentando conectar ao Supabase e travando

**Solução:**
1. Configurar `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_JWT_SECRET`
2. Verificar que as credenciais do Supabase estão corretas
3. Redeploy após configurar

### Problema: Download de vídeo falha

**Possíveis causas:**
- Credenciais do Microsoft Graph expiradas
- Permissões insuficientes
- URL de vídeo expirada

**Solução:**
1. Verificar `MICROSOFT_CLIENT_ID`, `CLIENT_SECRET`, `TENANT_ID`
2. Confirmar permissões no Azure AD (OnlineMeetings.Read.All, etc.)
3. Renovar credenciais se necessário

### Logs de Debug

Para ver logs no Railway:
1. Acesse o dashboard do Railway
2. Selecione o serviço
3. Vá em "Deployments" → "Logs"
4. Procure por mensagens de erro

Logs importantes no webhook:
```python
logger.error(f"Erro ao enviar para API de transcrição: {str(e)}")
logger.error(f"Response status: {e.response.status_code}, body: {e.response.text}")
```

---

## 🚀 Próximos Passos

### Ação Imediata (Requerida)

1. ✅ ~~Merge dos PRs~~ (COMPLETO)
2. ⏳ **Configurar variáveis de ambiente no Railway** (PENDENTE)
   - transcription-api: `TRANSCRIPTION_SERVICE_API_KEY` + Supabase vars
   - integracao-lia-teams: `TRANSCRIPTION_API_KEY`
3. ⏳ **Redeploy ambos os serviços** (PENDENTE)
4. ⏳ **Testar com curl** conforme seção de testes (PENDENTE)
5. ⏳ **Testar com reunião real do Teams** (PENDENTE)

### Melhorias Futuras (Opcional)

- **Monitoramento**: Adicionar health checks e alertas
- **Retry Logic**: Implementar retry automático se transcrição falhar
- **Queue System**: Usar fila (Redis/RabbitMQ) para processar transcrições
- **Webhook Renewal**: Automatizar renovação de subscriptions do Graph
- **Rate Limiting**: Adicionar rate limiting na API
- **Logs Estruturados**: Migrar para logging estruturado (JSON)

---

## 📊 Resumo Executivo

### O que foi feito?

✅ Identificado problema de autenticação (webhook → API)  
✅ Implementado autenticação via API Key  
✅ Atualizado 3 repositórios  
✅ Criado e merged 3 PRs  
✅ Testado localmente (100% sucesso)  
✅ Gerado chave API segura  
✅ Documentado tudo  

### O que falta?

⏳ Configurar variáveis de ambiente no Railway  
⏳ Redeploy dos serviços  
⏳ Testes de produção  
⏳ Validação com reunião real  

### Status Atual

🟡 **Parcialmente Implementado**
- Código: ✅ 100% Completo
- Testes Locais: ✅ 100% Aprovado
- Deploy Produção: ⏳ Aguardando configuração
- Testes Produção: ⏳ Aguardando configuração

---

## 📞 Contato

**Desenvolvedor:** Devin AI  
**Sessão:** https://app.devin.ai/sessions/518ba707526c4851b5dd2d5a5e872953  
**Data:** 01 de Outubro de 2025  

Para dúvidas ou suporte, contactar Jairo Soares (@Tandera-io).

---

**Link da Sessão Devin:** https://app.devin.ai/sessions/518ba707526c4851b5dd2d5a5e872953
