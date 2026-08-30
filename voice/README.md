# Voz por central Asterisk (alternativa ao torpedo de operadora)

Central telefônica em container que se registra num ramal SIP e toca um áudio
gerado por TTS numa ligação — útil quando a operadora não oferece (ou bloqueia)
o disparo de voz automatizado pela API.

## Preparar

1. Em `config/pjsip.conf`, substitua `SEU_RAMAL_SIP` e `SUA_SENHA_SIP` pelos
   dados do seu ramal (o painel da operadora mostra os dois, junto do servidor).
2. Gere o áudio a partir do texto do aviso:

       say -v Luciana -o /tmp/aviso.aiff "Sua entrega chega hoje as 15 horas."
       afconvert -f WAVE -d LEI16@8000 -c 1 /tmp/aviso.aiff sounds/aviso.wav

   (`say` e `afconvert` são nativos do macOS; em Linux use `espeak` + `ffmpeg`.)

## Rodar

    docker run -d --name lig-asterisk \
      -p 5060:5060/udp -p 10000-10020:10000-10020/udp \
      -v "$PWD/voice/config/pjsip.conf:/etc/asterisk/pjsip.conf:ro" \
      -v "$PWD/voice/config/extensions.conf:/etc/asterisk/extensions.conf:ro" \
      -v "$PWD/voice/config/rtp.conf:/etc/asterisk/rtp.conf:ro" \
      -v "$PWD/voice/sounds/aviso.wav:/var/lib/asterisk/sounds/en/aviso.wav:ro" \
      andrius/asterisk:latest

Confira o registro e dispare uma ligação de teste:

    docker exec lig-asterisk asterisk -rx "pjsip show registrations"
    docker exec lig-asterisk asterisk -rx \
      "channel originate PJSIP/DDDNUMERO@nvoip application Playback aviso"

## Diagnóstico

    docker exec lig-asterisk asterisk -rx "pjsip set logger on"
    docker logs lig-asterisk 2>&1 | grep -E "INVITE sip:|SIP/2.0 [0-9]{3}"

Erros comuns na resposta ao INVITE:

| Resposta | Significado |
|---|---|
| `401` seguido de novo INVITE | normal — é o desafio de autenticação |
| `403 Forbidden auth ID` | o campo `From` precisa ser o ramal, não o número virtual |
| `404 Conta nao encontrada` | a operadora não roteia chamadas de saída para esta conta |

O último caso não se resolve por configuração: depende de liberação da operadora.
