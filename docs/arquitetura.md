# Sistema de Notificação por Voz + Bot de WhatsApp — Especificação

Status: implementado e validado em produção

## Objetivo

Quando um sistema externo (ERP, agenda, e-commerce) registra um evento que o
cliente precisa saber, este serviço:

1. Liga para o cliente com uma mensagem de voz automatizada (TTS) via Nvoip,
   convidando-o a continuar pelo WhatsApp.
2. Quando o cliente chama no WhatsApp, um bot conversacional responde
   com o contexto do aviso daquele telefone, em texto livre, registrando toda a
   conversa.

Caso de uso: **aviso/notificação + atendimento** (não é venda ativa — sem
exigência de prefixo 0303 da Anatel).

## Decisões de arquitetura (e por quê)

| Decisão | Motivo |
|---|---|
| **Voz via Twilio** (`POST /Calls.json` com TwiML `<Say>`) — provedor ativo | Validado em produção: liga do número +55 (11) 5028-6739 e fala em pt-BR (voz Polly.Camila). A Nvoip permaneceu bloqueada pela operadora em todos os protocolos (torpedo, SIP saída/entrada). |
| Nvoip mantida como alternativa (`VOICE_PROVIDER=nvoip`) | Número +55 imediato no painel; API de TTS confirmada nos SDKs oficiais (GitHub Nvoip). |
| WhatsApp via **Evolution API** (não oficial, self-hosted) | A API pública da Nvoip só envia templates (`/wa/sendTemplates`) — não recebe mensagens. A Meta oficial foi descartada pelo usuário. Evolution dá webhook de entrada + envio de texto livre em minutos, grátis. |
| Bot via **OpenRouter** (`minimax/minimax-m3:free`) | API compatível com OpenAI, chamada por httpx; modelo gratuito validado em pt-BR (o `openai/gpt-oss-20b:free` foi descontinuado pela OpenRouter). |
| Python 3.12+ / FastAPI, serviço único | Escolha do usuário. Dois lados no mesmo processo: API de disparo + webhook do bot. |
| SQLite (stdlib `sqlite3`) | Volume de MVP; zero infraestrutura. Endpoints FastAPI síncronos (`def`) rodam no threadpool — sem async no acesso a dados. |
| Modo `DRY_RUN` | Testar o fluxo inteiro sem gastar créditos nem ter contas configuradas: provedores viram logs; bot testável via endpoint de dev. |

### Risco assumido (explícito)

Evolution API viola os termos do WhatsApp; o número conectado pode ser banido.
Mitigações: número dedicado (nunca o pessoal do usuário), bot apenas responde
conversas iniciadas pelo cliente, e o transporte fica isolado atrás de uma
interface — migrar para Meta Cloud API troca um adaptador, não o bot.

## Arquitetura

```
sistema externo                     celular do cliente
     │ POST /api/notifications           │  WhatsApp
     ▼                                   ▼
┌─────────────────────────┐      ┌──────────────────┐
│  app FastAPI (host)     │◄─────│  Evolution API   │ webhook messages.upsert
│                         │─────►│  (Docker, :8080) │ POST /message/sendText
│  ┌───────────────────┐  │      └──────────────────┘
│  │ motor de conversa │──┼──► OpenRouter (minimax-m3:free)
│  └───────────────────┘  │
│  SQLite (avisos,        │─────► API Nvoip (torpedo de voz TTS)
│  mensagens)             │
└─────────────────────────┘
```

Evolution API roda via `docker-compose` (imagem `evoapicloud/evolution-api` +
PostgreSQL + Redis, conforme compose oficial do projeto). O app FastAPI roda no
host durante o MVP (`uvicorn`), na mesma máquina — o webhook aponta para
`http://host.docker.internal:8000` (macOS).

## Estrutura de arquivos

```
ligacao/
├── app/
│   ├── __init__.py
│   ├── main.py            # criação do FastAPI, rotas incluídas
│   ├── config.py          # Settings via variáveis de ambiente (.env)
│   ├── db.py              # conexão SQLite, schema, funções de acesso
│   ├── routes/
│   │   ├── notifications.py   # POST /api/notifications (auth X-API-Key)
│   │   ├── webhook.py         # POST /webhooks/whatsapp (Evolution)
│   │   └── dev.py             # POST /dev/chat (só quando DRY_RUN/DEV)
│   ├── providers/
│   │   ├── nvoip.py       # send_voice_torpedo(caller, called, texto)
│   │   └── evolution.py   # send_text(number, text)
│   └── bot/
│       ├── engine.py      # monta contexto + chama o modelo + fallback de erro
│       └── llm.py         # cliente da OpenRouter (chat completions)
├── tests/                 # pytest; provedores sempre falsos/gravados
├── docker-compose.yml     # stack Evolution API (api + postgres + redis)
├── .env.example
├── requirements.txt
└── README.md              # setup passo a passo (painéis Nvoip, QR code, etc.)
```

Cada unidade responde: o que faz, como se usa, de que depende — provedores não
conhecem o banco; o motor não conhece HTTP; rotas orquestram.

## Contratos

### `POST /api/notifications` — dispara o aviso

Auth: header `X-API-Key: <API_KEY>` (comparação em tempo constante).

Request:
```json
{
  "phone": "5532999999999",
  "voice_message": "Olá! Seu pedido 123 saiu para entrega hoje. Para detalhes, chame no nosso WhatsApp.",
  "context": "Pedido 123 do cliente João, entrega prevista 29/08 à tarde, transportadora XYZ."
}
```

- `phone`: E.164 sem `+` (DDI+DDD+número). Validação: dígitos, 12–13 chars, começa com 55.
- `voice_message`: o que o TTS fala na ligação (obrigatório).
- `context` (opcional): texto livre que o bot usa para responder — não é falado.

Response `201`: `{"id": 1, "status": "sent" | "dry_run", "nvoip": {...resposta crua...}}`
Erros: `401` sem chave válida; `422` payload inválido; `502` falha na Nvoip
(corpo inclui o erro; quem chamou decide reenviar — sem retry automático no MVP).

### Nvoip (provider)

- Autenticação: `NVOIP_NAPIKEY` (painel → API) por query param na API v2 —
  validado em conta real (o grant OAuth e o Bearer v3 foram recusados pelas
  credenciais emitidas no painel do usuário). `NVOIP_ACCESS_TOKEN` Bearer na
  v3 permanece como alternativa.
- Chamada: `POST https://api.nvoip.com.br/v2/torpedo/voice?napikey=...`
  (mesmo payload da v3; `caller` = numbersip da conta)
  ```json
  {"caller": "<NVOIP_CALLER>", "called": "<phone>",
   "audios": [{"audio": "<voice_message>", "positionAudio": 1}], "dtmfs": []}
  ```
- DTMF interativo (`dtmfs`) fica fora do MVP (fase 2).

### `POST /webhooks/whatsapp` — entrada do bot

Recebe eventos da Evolution API. Regras:

- Processa apenas `event == "messages.upsert"` com `fromMe == false` e corpo de
  texto; qualquer outra coisa → `200` e ignora (áudio/imagem recebem resposta
  fixa "por enquanto só entendo texto").
- Extração defensiva: o payload da Evolution varia entre versões
  (`data.key.remoteJid` vs `data.message.key.remoteJid`); um normalizador tenta
  os caminhos conhecidos e loga o payload cru quando não reconhece (e responde
  `200` — nunca 500 para o webhook, para não gerar reenvio em loop).
- Telefone = `remoteJid` sem sufixo `@s.whatsapp.net`. Grupos
  (`@g.us`) são ignorados.
- Segurança: rota exige `?token=<WEBHOOK_TOKEN>` na URL configurada na
  Evolution (segredo aleatório gerado no setup).
- Resposta ao cliente: enviada via provider Evolution
  (`POST {EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}`, header
  `apikey`, corpo `{"number": ..., "text": ...}`).

### Motor de conversa (`bot/engine.py`)

Entrada: `phone`, `text`. Saída: resposta em texto (nunca lança para a rota).

1. Grava a mensagem recebida (`direction=in`).
2. Monta o prompt:
   - System: persona de atendente da empresa (nome configurável
     `BUSINESS_NAME`), pt-BR, respostas curtas de WhatsApp, usar somente o
     contexto disponível, não inventar dados, oferecer atendimento humano
     quando não souber.
   - Contexto: até 3 avisos mais recentes daquele telefone (mensagem de voz +
     `context`), com data.
   - Histórico: últimas 20 mensagens daquele telefone.
3. Chama a OpenRouter (`POST {base}/chat/completions`, `max_tokens=1024`),
   com o system prompt como primeira mensagem.
   Respostas técnicas anteriores (eco `[sem IA]` e fallback) são excluídas do
   histórico enviado — o modelo imita o que vê no prompt.
4. Grava a resposta (`direction=out`) e retorna.
5. Qualquer exceção → loga e retorna mensagem padrão ("Tive um problema
   técnico agora — pode tentar de novo em instantes?").

### Banco (SQLite)

```sql
notifications(id INTEGER PK, phone TEXT, voice_message TEXT, context TEXT,
              status TEXT, nvoip_response TEXT, created_at TEXT)
messages(id INTEGER PK, phone TEXT, direction TEXT CHECK(in|out), text TEXT,
         created_at TEXT)
```

Arquivo `data/ligacao.db` (gitignored). Sem migrações formais no MVP —
`CREATE TABLE IF NOT EXISTS` no startup.

### `POST /dev/chat` (apenas `DEV_MODE=true`)

`{"phone": "...", "text": "..."}` → passa pelo motor real e retorna a resposta
do bot no corpo. Permite conversar com o bot pelo terminal antes de existir
WhatsApp conectado.

## Configuração (`.env`)

```
API_KEY=                  # chave que o sistema disparador usa
OPENROUTER_API_KEY=
NVOIP_ACCESS_TOKEN=
NVOIP_CALLER=             # número Nvoip do usuário (formato DDI+DDD+num)
EVOLUTION_URL=http://localhost:8080
EVOLUTION_APIKEY=         # AUTHENTICATION_API_KEY do container
EVOLUTION_INSTANCE=ligacao
WEBHOOK_TOKEN=            # segredo da rota do webhook
BUSINESS_NAME=
DRY_RUN=true              # provedores viram logs
DEV_MODE=true             # habilita /dev/chat
```

`DRY_RUN=true` → `nvoip.py` e `evolution.py` logam a chamada que fariam e
retornam sucesso simulado. O motor de IA roda de verdade (é barato e é o que
se quer validar); sem `OPENROUTER_API_KEY`, o motor responde eco marcado
`[sem IA]`.

## Testes (pytest, TDD)

- Providers: montagem correta de URL/headers/payload (com `httpx.MockTransport`
  ou monkeypatch de transporte); comportamento DRY_RUN.
- Rotas: auth (401/422/201), webhook ignora `fromMe`/grupos/eventos estranhos,
  normalizador cobre os dois formatos de payload conhecidos, sempre 200.
- Motor: injeta cliente de LLM falso; verifica contexto no prompt, gravação
  in/out, fallback em exceção.
- Banco: em arquivo temporário por teste.
- Nenhum teste toca rede real.

## Fora de escopo do MVP

Painel/visualização de conversas; retry/fila de disparos; múltiplas instâncias
WhatsApp; DTMF interativo na ligação; envio ativo de WhatsApp (templates);
transferência para atendente humano (o bot apenas sugere contato); deploy em
servidor (roda na máquina do usuário; deploy é fase posterior documentada no
README).

## Fases de entrega

1. **Core testável**: app completo com DRY_RUN + testes verdes + `/dev/chat`
   conversando com o modelo de verdade.
2. **WhatsApp real**: docker-compose da Evolution, criação da instância, QR
   code, webhook local, conversa real de ponta a ponta.
3. **Voz real**: `DRY_RUN=false` para Nvoip, torpedo de teste no telefone do
   usuário.
4. **Integração**: sistema externo chamando `/api/notifications` com a chave.
