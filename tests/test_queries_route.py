def criar_aviso(client, phone="5511987654321", msg="Sua entrega chega hoje"):
    r = client.post("/api/notifications", json={"phone": phone, "voice_message": msg},
                    headers={"X-API-Key": "test-key"})
    assert r.status_code == 201
    return r.json()["id"]


def test_consulta_exige_chave(client):
    resposta = client.get("/api/notifications/1")
    assert resposta.status_code == 401


def test_aviso_inexistente_retorna_404(client):
    resposta = client.get("/api/notifications/999", headers={"X-API-Key": "test-key"})
    assert resposta.status_code == 404


def test_retorna_status_do_aviso(client):
    aviso_id = criar_aviso(client)
    resposta = client.get(f"/api/notifications/{aviso_id}", headers={"X-API-Key": "test-key"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["id"] == aviso_id
    assert corpo["phone"] == "5511987654321"
    assert corpo["voice_message"] == "Sua entrega chega hoje"
    assert corpo["status"] == "dry_run"
    assert "created_at" in corpo


def test_atualiza_status_consultando_o_provedor(client):
    """Quando há id de chamada, o desfecho vem do provedor, não do banco."""
    class ProvedorComStatus:
        def send_voice_torpedo(self, called, message):
            return {"sid": "CA123", "status": "queued"}

        def call_status(self, call_sid):
            assert call_sid == "CA123"
            return {"status": "completed", "duration": 12, "answered": True}

    client.app.state.nvoip = ProvedorComStatus()
    aviso_id = criar_aviso(client)

    corpo = client.get(f"/api/notifications/{aviso_id}",
                       headers={"X-API-Key": "test-key"}).json()
    assert corpo["call"] == {"status": "completed", "duration": 12, "answered": True}


def test_conversa_exige_chave(client):
    assert client.get("/api/conversations/5511987654321").status_code == 401


def test_retorna_conversa_do_cliente(client):
    client.app.state.db.save_message("5511987654321", "in", "oi")
    client.app.state.db.save_message("5511987654321", "out", "olá! como posso ajudar?")
    client.app.state.db.save_message("5511900000000", "in", "de outro cliente")

    corpo = client.get("/api/conversations/5511987654321",
                       headers={"X-API-Key": "test-key"}).json()
    assert corpo["phone"] == "5511987654321"
    assert [(m["direction"], m["text"]) for m in corpo["messages"]] == [
        ("in", "oi"), ("out", "olá! como posso ajudar?")]


def test_conversa_encontra_telefone_sem_nono_digito(client):
    client.app.state.db.save_message("5511987654321", "in", "mensagem gravada com 13 dígitos")
    corpo = client.get("/api/conversations/551187654321",
                       headers={"X-API-Key": "test-key"}).json()
    assert len(corpo["messages"]) == 1


def test_conversa_vazia_nao_e_erro(client):
    corpo = client.get("/api/conversations/5511911112222",
                       headers={"X-API-Key": "test-key"}).json()
    assert corpo["messages"] == []
