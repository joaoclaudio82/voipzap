from app.db import Database


def make_db(tmp_path):
    return Database(str(tmp_path / "sub" / "test.db"))


def test_save_and_list_notifications(tmp_path):
    db = make_db(tmp_path)
    i1 = db.save_notification("5532988887777", "msg 1", "ctx 1", "sent", "{}")
    i2 = db.save_notification("5532988887777", "msg 2", None, "dry_run", "{}")
    db.save_notification("5511900000000", "outro tel", None, "sent", "{}")
    assert i2 > i1
    rows = db.recent_notifications("5532988887777")
    assert len(rows) == 2
    assert rows[0]["voice_message"] == "msg 2"  # mais recente primeiro
    assert rows[0]["context"] is None
    assert rows[1]["context"] == "ctx 1"


def test_recent_notifications_limit(tmp_path):
    db = make_db(tmp_path)
    for i in range(5):
        db.save_notification("5532988887777", f"msg {i}", None, "sent", "{}")
    assert len(db.recent_notifications("5532988887777", limit=3)) == 3


def test_messages_chronological_with_limit(tmp_path):
    db = make_db(tmp_path)
    for i in range(25):
        db.save_message("5532988887777", "in" if i % 2 == 0 else "out", f"m{i}")
    rows = db.recent_messages("5532988887777", limit=20)
    assert len(rows) == 20
    assert rows[0]["text"] == "m5"   # as 20 últimas, em ordem cronológica
    assert rows[-1]["text"] == "m24"
    assert rows[-1]["direction"] == "in"


def test_finds_notification_across_ninth_digit_variants(tmp_path):
    """Aviso disparado com 13 dígitos deve ser achado pelo WhatsApp com 12."""
    db = make_db(tmp_path)
    db.save_notification("5511987654321", "Pedido 789 sai hoje", "ctx", "sent", "{}")
    achados = db.recent_notifications("551187654321")
    assert len(achados) == 1
    assert achados[0]["voice_message"] == "Pedido 789 sai hoje"


def test_history_merges_ninth_digit_variants(tmp_path):
    db = make_db(tmp_path)
    db.save_message("5511987654321", "in", "primeira pelo formato longo")
    db.save_message("551187654321", "in", "segunda pelo formato curto")
    rows = db.recent_messages("5511987654321")
    assert [r["text"] for r in rows] == ["primeira pelo formato longo", "segunda pelo formato curto"]
