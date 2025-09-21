# Integração LIA Teams - Azure Function App

Este repositório contém uma Azure Function App para integração com Microsoft Teams.

## Estrutura do Projeto

- `CopyGraphToBlob/` - Função principal que copia dados do Microsoft Graph para Azure Blob Storage
- `host.json` - Configurações do host da Azure Function
- `requirements.txt` - Dependências Python necessárias
- `local.settings.json.example` - Exemplo de configurações locais

## Configuração

1. Copie o arquivo `local.settings.json.example` para `local.settings.json`
2. Configure suas credenciais do Azure Storage Account:
   - `AzureWebJobsStorage`: String de conexão completa do Azure Storage
   - `STORAGE_ACCOUNT_NAME`: Nome da sua conta de armazenamento

## Instalação

```bash
pip install -r requirements.txt
```

## Execução Local

```bash
func start
```

## Função CopyGraphToBlob

Esta função é responsável por copiar dados do Microsoft Graph API para o Azure Blob Storage, facilitando a integração entre Microsoft Teams e outros sistemas.
