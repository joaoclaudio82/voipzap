# ligacao — aviso por ligação + atendimento por WhatsApp

Quando o seu sistema registra um evento (entrega, pedido, agendamento), este
serviço **liga para o cliente** com uma mensagem de voz (TTS, via Twilio) que
convida a continuar no **WhatsApp**, onde um **bot com IA (OpenRouter)** responde
com o contexto do aviso. Tudo fica registrado em um banco SQLite local.

Arquitetura e decisões: [docs/arquitetura.md](docs/arquitetura.md)

> **Atenção:** o WhatsApp usa a Evolution API (não oficial). O número conectado
> pode ser banido pelo WhatsApp — use um número dedicado, nunca o seu pessoal.

## Requisitos

- Python 3.11+ · Docker Desktop (só para a fase do WhatsApp)
- Conta Twilio com número +55 e saldo (fase de voz) — a Nvoip segue como alternativa
- Chave da API da OpenRouter (`OPENROUTER_API_KEY`) — há modelos gratuitos

## Fase 1 — rodar localmente (sem custo)

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env        # edite: API_KEY, OPENROUTER_API_KEY, BUSINESS_NAME
    pytest                      # tudo verde
    uvicorn --factory app.main:create_app --reload

Teste o bot no terminal (sem WhatsApp):

    curl -s localhost:8000/dev/chat -X POST -H 'Content-Type: application/json' \
      -d '{"phone": "5532988887777", "text": "oi, quem é você?"}'

Simule um disparo (com `DRY_RUN=true` nada é cobrado):

    curl -s localhost:8000/api/notifications -X POST \
      -H 'Content-Type: application/json' -H "X-API-Key: $API_KEY" \
      -d '{"phone": "5532988887777", "voice_message": "Sua entrega chega hoje às 15h. Dúvidas, chame no nosso WhatsApp.", "context": "Pedido 123, transportadora XYZ"}'

Depois do disparo, pergunte ao bot "cadê meu pedido?" no /dev/chat — ele deve
responder usando o contexto do aviso.

## Fase 2 — conectar o WhatsApp

1. `docker compose up -d` (Evolution API em :8080, manager em :3000)
2. Criar a instância:

       curl -s localhost:8080/instance/create -X POST \
         -H "apikey: $EVOLUTION_APIKEY" -H 'Content-Type: application/json' \
         -d '{"instanceName": "ligacao", "integration": "WHATSAPP-BAILEYS", "qrcode": true}'

3. Pegar o QR code: abra `http://localhost:3000` (manager), conecte na API com
   a URL `http://localhost:8080` e a `EVOLUTION_APIKEY`, abra a instância
   `ligacao` e escaneie o QR com o WhatsApp do número dedicado
   (Configurações → Dispositivos conectados).
4. Registrar o webhook apontando para o app no host:

       curl -s localhost:8080/webhook/set/ligacao -X POST \
         -H "apikey: $EVOLUTION_APIKEY" -H 'Content-Type: application/json' \
         -d '{"webhook": {"enabled": true, "url": "http://host.docker.internal:8000/webhooks/whatsapp?token=SEU_WEBHOOK_TOKEN", "events": ["MESSAGES_UPSERT"]}}'

   (Troque `SEU_WEBHOOK_TOKEN` pelo valor de `WEBHOOK_TOKEN` do `.env`. Se o
   comando retornar erro de formato, o shape do corpo varia entre versões da
   Evolution — registre o webhook pela interface do manager em :3000, que
   oferece a mesma configuração em tela.)
5. Mande um "oi" de outro celular para o número conectado — o bot deve
   responder. Os logs do app mostram o fluxo.

Se o formato do payload do webhook não for reconhecido, o app loga o payload
cru e responde 200 — ajuste o parser em `app/routes/webhook.py` com base no log.

## Fase 3 — ligar a voz de verdade (Twilio, recomendado)

1. No painel do Twilio: compre um número **+55 com capacidade de voz** e anote
   `Account SID` e `Auth Token`.
2. No `.env`: `VOICE_PROVIDER=twilio`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
   `TWILIO_CALLER=+55...` e `DRY_RUN=false`.
3. Dispare o curl da Fase 1 para o SEU celular: você recebe a ligação com a
   mensagem falada em português (voz `Polly.Camila`).
   Custo aproximado: US$ 0,066/min para celular no Brasil + US$ 1,15/mês pelo número.

## Fase 3b — voz pela Nvoip (quando a operadora liberar)

1. No painel Nvoip, seção **API**, copie a `napikey` e o `numbersip`; garanta
   **saldo de créditos** na conta (sem saldo a ligação não sai).
2. No `.env`: preencha `NVOIP_NAPIKEY`, `NVOIP_CALLER` (numbersip; se a Nvoip
   recusar, use o número virtual completo) e mude `DRY_RUN=false`.
3. Reinicie o app e dispare um aviso para o SEU próprio celular (curl da Fase 1).
   Você deve receber a ligação com a mensagem em TTS. Cada disparo consome
   créditos Nvoip.
4. Verificação rápida de credenciais sem custo:
   `curl -sG https://api.nvoip.com.br/v2/balance --data-urlencode "napikey=$NVOIP_NAPIKEY"`
   deve responder `{"balance": ...}`.

## Fase 4 — integrar o seu sistema

Seu sistema chama `POST /api/notifications` com o header `X-API-Key` (valor de
`API_KEY` do `.env`) e o JSON `{phone, voice_message, context}`. Respostas:
`201` disparado, `401` chave errada, `422` telefone/payload inválido, `502`
falha na Nvoip (pode reenviar).

## Operação

- Banco: `data/ligacao.db` (SQLite). Conversas: tabela `messages`; avisos:
  `notifications`.
- O bot responde apenas quem inicia conversa; mídia recebe resposta fixa;
  grupos são ignorados.
- Para migrar do transporte não oficial para a Meta Cloud API no futuro,
  substitua `app/providers/evolution.py` e o parser do webhook — o motor do
  bot não muda.
