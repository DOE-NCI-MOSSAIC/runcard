"""Smoke tests to verify the environment is working."""

import runcard


def test_version() -> None:
    assert runcard.__version__ == "0.1.0"


def test_polars_available() -> None:
    import polars as pl

    df = pl.DataFrame({"x": [1, 2, 3]})
    assert df.shape == (3, 1)


def test_orjson_available() -> None:
    import orjson

    data = orjson.dumps({"key": "value"})
    assert orjson.loads(data) == {"key": "value"}


def test_pydantic_available() -> None:
    from pydantic import BaseModel

    class Sample(BaseModel):
        name: str
        value: float

    s = Sample(name="test", value=3.14)
    assert s.name == "test"
