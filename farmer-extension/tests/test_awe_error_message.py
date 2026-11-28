from openg2p_registry_farmer_extension.awe_error_message import awe_error_message


def test_a_plain_sentence_is_kept():
    assert awe_error_message(400, "A comment is required to reject") == "A comment is required to reject."


def test_raw_json_and_internal_urls_are_replaced():
    for reply in ('{"detail": "boom", "code": "X"}', "Client error for url http://awe.commons:8080/v1/tasks/1",
                  "AWE_TASK_NOT_FOUND"):
        text = awe_error_message(500, reply)
        assert "{" not in text and "http" not in text and "_" not in text
        assert "approval service" in text


def test_status_codes_say_what_to_do():
    assert "permission" in awe_error_message(403, "")
    assert "not found" in awe_error_message(404, "{}")
    assert "refresh" in awe_error_message(409, "[]").lower()
