from app.phones import variants


def test_adds_ninth_digit_variant():
    assert set(variants("551187654321")) == {"551187654321", "5511987654321"}


def test_removes_ninth_digit_variant():
    assert set(variants("5511987654321")) == {"5511987654321", "551187654321"}


def test_landline_has_no_ninth_digit_variant():
    # fixo de SP: 55 + 11 + 8 dígitos começando com 5 (não é celular)
    assert variants("551150286739") == ["551150286739"]


def test_non_brazilian_number_is_untouched():
    assert variants("14155238886") == ["14155238886"]


def test_strips_plus_and_keeps_digits():
    assert "5511987654321" in variants("+5511987654321")
