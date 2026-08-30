import logging

from app.config import Settings
from app.db import Database

logger = logging.getLogger(__name__)

FALLBACK_REPLY = "Tive um problema técnico agora — pode tentar de novo em instantes?"
ECHO_PREFIX = "[sem IA] Recebi: "

_SYSTEM_TEMPLATE = """Você é o assistente de atendimento de {business_name} no WhatsApp.

Regras:
- Responda sempre em português brasileiro, em tom cordial e direto.
- Respostas curtas, adequadas ao WhatsApp (1 a 4 frases).
- Use SOMENTE as informações dos avisos abaixo e da conversa. Não invente dados,
  prazos, valores ou políticas.
- Se não souber responder, diga isso e ofereça acionar um atendente humano.

{context_block}"""


def _is_technical_reply(text: str) -> bool:
    return text == FALLBACK_REPLY or text.startswith(ECHO_PREFIX)


class BotEngine:
    def __init__(self, settings: Settings, db: Database, client=None):
        self.settings = settings
        self.db = db
        self.client = client

    def handle_message(self, phone: str, text: str) -> str:
        saved = self._try_save(phone, "in", text)
        if self.client is None:
            reply = f"{ECHO_PREFIX}{text}"
        else:
            try:
                reply = self._ask_llm(phone, pending_text=None if saved else text)
            except Exception:
                logger.exception("erro ao chamar o modelo para %s", phone)
                reply = FALLBACK_REPLY
        self._try_save(phone, "out", reply)
        return reply

    def _try_save(self, phone: str, direction: str, text: str) -> bool:
        try:
            self.db.save_message(phone, direction, text)
            return True
        except Exception:
            logger.exception("falha ao gravar mensagem '%s' de %s", direction, phone)
            return False

    def _ask_llm(self, phone: str, pending_text: str | None = None) -> str:
        reply = self.client.complete(
            self._build_system(phone), self._build_messages(phone, pending_text)
        )
        return reply.strip() or FALLBACK_REPLY

    def _build_system(self, phone: str) -> str:
        notifications = self.db.recent_notifications(phone, limit=3)
        if notifications:
            lines = ["Avisos recentes enviados a este cliente (mais recente primeiro):"]
            for n in notifications:
                lines.append(f"- [{n['created_at']}] Ligação: {n['voice_message']}")
                if n["context"]:
                    lines.append(f"  Contexto interno: {n['context']}")
            context_block = "\n".join(lines)
        else:
            context_block = "Não há avisos registrados para este cliente."
        return _SYSTEM_TEMPLATE.format(
            business_name=self.settings.business_name, context_block=context_block
        )

    def _build_messages(self, phone: str, pending_text: str | None = None) -> list[dict]:
        # A mensagem recebida já foi gravada; o histórico inclui a fala atual.
        # Se a gravação falhou, pending_text a repõe no fim do prompt.
        history = self.db.recent_messages(phone, limit=20)
        messages: list[dict] = []
        for row in history:
            # Respostas técnicas ficam no banco para auditoria, mas fora do
            # prompt: o modelo imita o que vê no histórico.
            if row["direction"] == "out" and _is_technical_reply(row["text"]):
                continue
            role = "user" if row["direction"] == "in" else "assistant"
            if messages and messages[-1]["role"] == role:
                messages[-1]["content"] += "\n" + row["text"]
            else:
                messages.append({"role": role, "content": row["text"]})
        if pending_text is not None:
            if messages and messages[-1]["role"] == "user":
                messages[-1]["content"] += "\n" + pending_text
            else:
                messages.append({"role": "user", "content": pending_text})
        while messages and messages[0]["role"] == "assistant":
            messages.pop(0)
        return messages
