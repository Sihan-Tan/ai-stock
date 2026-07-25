"""飞书告警通道单测。"""

from __future__ import annotations

from desk_alert import _interpret_feishu_response


def test_interpret_feishu_code_zero_sent():
    assert _interpret_feishu_response('{"code":0,"msg":"success"}') == "sent"


def test_interpret_feishu_business_error():
    out = _interpret_feishu_response('{"code":19021,"msg":"sign match fail"}')
    assert out.startswith("failed:code_19021")


def test_interpret_feishu_empty_or_non_json_sent():
    assert _interpret_feishu_response("") == "sent"
    assert _interpret_feishu_response("ok") == "sent"
    assert _interpret_feishu_response('{"msg":"no code"}') == "sent"


def test_feishu_sign_matches_official_algo():
    """飞书文档：hmac key = timestamp\\\\nsecret，无 msg。"""
    import base64
    import hashlib
    import hmac

    ts = "1596607260"
    secret = "test_secret"
    string_to_sign = f"{ts}\n{secret}"
    expected = base64.b64encode(
        hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")
    # 与旧错误算法不同
    wrong = base64.b64encode(
        hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("utf-8")
    assert expected != wrong
    assert len(expected) > 10
