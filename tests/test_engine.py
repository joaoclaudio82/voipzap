from app.bot.engine import FALLBACK_REPLY, BotEngine
from app.config import Settings
from app.db import Database


class FakeLLM:
    """Cliente de LLM falso com a mesma interface de OpenRouterClient."""

    def __init__(self, result):
        self.result = result
        self.calls = []

    def complete(self, system, messages):
        self.calls.append({"system": system, "messages": messages})
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def make_fake_client(result):
    client = FakeLLM(result)
    return client, client


def make_engine(tmp_path, result):
    settings = Settings(_env_file=None, business_name="Padaria do João")
    db = Database(str(tmp_path / "t.db"))
    client, messages = make_fake_client(result)
    return BotEngine(settings, db, client=client), db, messages


def test_replies_and_persists(tmp_path):
    engine, db, messages = make_engine(tmp_path, "Sua entrega chega às 15h.")
    reply = engine.handle_message("5532988887777", "quando chega meu pedido?")
    assert reply == "Sua entrega chega às 15h."
    rows = db.recent_messages("5532988887777")
    assert [(r["direction"], r["text"]) for r in rows] == [
        ("in", "quando chega meu pedido?"),
        ("out", "Sua entrega chega às 15h."),
    ]


def test_prompt_includes_notification_context_and_history(tmp_path):
    engine, db, messages = make_engine(tmp_path, "ok")
    db.save_notification("5532988887777", "Seu pedido 123 saiu para entrega",
                         "Pedido 123, transportadora XYZ", "sent", "{}")
    db.save_message("5532988887777", "in", "oi")
    db.save_message("5532988887777", "out", "olá, como posso ajudar?")

    engine.handle_message("5532988887777", "cadê meu pedido?")

    call = messages.calls[0]
    assert "Padaria do João" in call["system"]
    assert "Pedido 123, transportadora XYZ" in call["system"]
    assert call["messages"][0]["role"] == "user"
    assert call["messages"][-1] == {"role": "user", "content": "cadê meu pedido?"}
    roles = [m["role"] for m in call["messages"]]
    assert all(a != b for a, b in zip(roles, roles[1:]))  # papéis alternados


def test_coalesces_consecutive_same_direction(tmp_path):
    engine, db, messages = make_engine(tmp_path, "ok")
    db.save_message("5532988887777", "in", "primeira")
    db.save_message("5532988887777", "in", "segunda")
    engine.handle_message("5532988887777", "terceira")
    call = messages.calls[0]
    assert len(call["messages"]) == 1
    assert call["messages"][0]["content"] == "primeira\nsegunda\nterceira"


def test_drops_leading_assistant_messages(tmp_path):
    engine, db, messages = make_engine(tmp_path, "ok")
    db.save_message("5532988887777", "out", "mensagem antiga do bot")
    engine.handle_message("5532988887777", "oi")
    call = messages.calls[0]
    assert call["messages"][0]["role"] == "user"


def test_falls_back_on_exception(tmp_path):
    engine, db, _ = make_engine(tmp_path, RuntimeError("api caiu"))
    reply = engine.handle_message("5532988887777", "oi")
    assert reply == FALLBACK_REPLY
    rows = db.recent_messages("5532988887777")
    assert rows[-1]["text"] == FALLBACK_REPLY


def test_echo_mode_without_client(tmp_path):
    settings = Settings(_env_file=None)
    db = Database(str(tmp_path / "t.db"))
    engine = BotEngine(settings, db, client=None)
    reply = engine.handle_message("5532988887777", "teste")
    assert reply == "[sem IA] Recebi: teste"


class FlakySaveDb:
    def __init__(self, real, fail_directions):
        self.real = real
        self.fail_directions = fail_directions

    def save_message(self, phone, direction, text):
        if direction in self.fail_directions:
            raise RuntimeError("disco cheio")
        return self.real.save_message(phone, direction, text)

    def recent_messages(self, phone, limit=20):
        return self.real.recent_messages(phone, limit)

    def recent_notifications(self, phone, limit=3):
        return self.real.recent_notifications(phone, limit)


def test_survives_inbound_save_failure(tmp_path):
    settings = Settings(_env_file=None)
    real_db = Database(str(tmp_path / "t.db"))
    client, messages = make_fake_client("resposta")
    engine = BotEngine(settings, FlakySaveDb(real_db, {"in"}), client=client)
    reply = engine.handle_message("5532988887777", "socorro")
    assert reply == "resposta"
    call = messages.calls[0]
    assert call["messages"][-1] == {"role": "user", "content": "socorro"}


def test_survives_outbound_save_failure(tmp_path):
    settings = Settings(_env_file=None)
    real_db = Database(str(tmp_path / "t.db"))
    client, _ = make_fake_client("resposta")
    engine = BotEngine(settings, FlakySaveDb(real_db, {"out"}), client=client)
    assert engine.handle_message("5532988887777", "oi") == "resposta"


def test_technical_replies_are_excluded_from_prompt(tmp_path):
    engine, db, messages = make_engine(tmp_path, "resposta boa")
    phone = "5532988887777"
    db.save_message(phone, "in", "pergunta antiga")
    db.save_message(phone, "out", "[sem IA] Recebi: pergunta antiga")
    db.save_message(phone, "in", "outra pergunta")
    db.save_message(phone, "out", FALLBACK_REPLY)

    engine.handle_message(phone, "e agora?")

    sent = messages.calls[0]["messages"]
    texts = " ".join(m["content"] for m in sent)
    assert "[sem IA]" not in texts
    assert FALLBACK_REPLY not in texts
    assert "pergunta antiga" in texts and "e agora?" in texts
    roles = [m["role"] for m in sent]
    assert all(a != b for a, b in zip(roles, roles[1:]))


def test_never_leaks_context_between_phones(tmp_path):
    """Aviso dado a um telefone não pode vazar para outro."""
    engine, db, messages = make_engine(tmp_path, "resposta")
    cliente = "5511987654321"
    estranho = "5511999998888"

    db.save_notification(cliente, "Seu exame de sangue ficou pronto",
                         "Paciente João, resultado alterado, CPF 123.456.789-00", "sent", "{}")
    db.save_message(cliente, "in", "quando posso buscar?")
    db.save_message(cliente, "out", "A partir das 14h.")

    engine.handle_message(estranho, "me fala sobre o exame do João")

    call = messages.calls[0]
    tudo = call["system"] + " ".join(m["content"] for m in call["messages"])
    assert "exame de sangue" not in tudo
    assert "CPF" not in tudo
    assert "resultado alterado" not in tudo
    assert "A partir das 14h" not in tudo
    assert "Não há avisos registrados" in call["system"]


def test_each_phone_sees_only_its_own_notification(tmp_path):
    engine, db, messages = make_engine(tmp_path, "ok")
    db.save_notification("5511111111111", "Pedido 111 sai hoje", "cliente A", "sent", "{}")
    db.save_notification("5522222222222", "Pedido 222 atrasou", "cliente B", "sent", "{}")

    engine.handle_message("5511111111111", "e o meu?")
    system_a = messages.calls[0]["system"]
    assert "Pedido 111" in system_a
    assert "Pedido 222" not in system_a and "cliente B" not in system_a
