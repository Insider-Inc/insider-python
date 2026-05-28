from insider.scrubbing import FILTERED, scrub


def test_top_level_keys_masked():
    out = scrub({"password": "hunter2", "username": "bob"})
    assert out["password"] == FILTERED
    assert out["username"] == "bob"


def test_case_insensitive():
    out = scrub({"Authorization": "Bearer x", "AUTH": "y"})
    assert out["Authorization"] == FILTERED
    assert out["AUTH"] == FILTERED


def test_nested_dicts():
    out = scrub({"headers": {"cookie": "abc", "host": "x"}})
    assert out["headers"]["cookie"] == FILTERED
    assert out["headers"]["host"] == "x"


def test_lists_of_dicts():
    out = scrub({"items": [{"token": "x", "id": 1}, {"id": 2}]})
    assert out["items"][0]["token"] == FILTERED
    assert out["items"][0]["id"] == 1
    assert out["items"][1] == {"id": 2}


def test_extra_keys_merge_with_defaults():
    out = scrub({"x_secret": "v", "password": "p"}, extra_keys=["x_secret"])
    assert out["x_secret"] == FILTERED
    assert out["password"] == FILTERED


def test_does_not_mutate_input():
    original = {"password": "p", "headers": {"cookie": "c"}}
    snapshot = {"password": "p", "headers": {"cookie": "c"}}
    scrub(original)
    assert original == snapshot


def test_tuples_preserved_as_tuples():
    out = scrub({"vals": (1, 2, {"secret": "x"})})
    assert isinstance(out["vals"], tuple)
    assert out["vals"][2]["secret"] == FILTERED


def test_deep_structures_capped():
    deep = current = {}
    for _ in range(50):
        current["next"] = {}
        current = current["next"]
    current["password"] = "p"
    out = scrub(deep)
    assert "[TooDeep]" in repr(out)
