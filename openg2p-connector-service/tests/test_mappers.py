import pytest

from openg2p_connector_service.mappers import JmesPathMapper, PassthroughMapper


def test_passthrough():
    m = PassthroughMapper()
    data = {"a": 1, "b": {"c": 2}}
    assert m.map(data) == data


def test_jmespath_basic():
    m = JmesPathMapper()
    data = {"outer": {"name": "Alice", "age": 30, "extra": True}}
    result = m.map(data, "{name: outer.name, age: outer.age}")
    assert result == {"name": "Alice", "age": 30}


def test_jmespath_none_expression():
    m = JmesPathMapper()
    data = {"a": 1}
    assert m.map(data, None) == data


def test_jmespath_non_dict_raises():
    m = JmesPathMapper()
    with pytest.raises(ValueError, match="must produce a dict"):
        m.map({"items": [1, 2]}, "items")
