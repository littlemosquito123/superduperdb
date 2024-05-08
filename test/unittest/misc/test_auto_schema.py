from test.db_config import DBConfig

import numpy as np
import pandas as pd
import pytest
import torch

from superduperdb.backends.ibis.query import Table
from superduperdb.backends.mongodb.query import Collection
from superduperdb.base.document import Document
from superduperdb.misc.auto_schema import infer_datatype, infer_schema


@pytest.fixture
def data():
    data = {
        "int": 1,
        "float": 1.0,
        "str": "1",
        "bool": True,
        "bytes": b"1",
        "np_array": np.array([1, 2, 3]),
        "torch_tensor": torch.tensor([1, 2, 3]),
        "dict": {"a": 1, "b": "2", "c": {"d": 3}},
        "dict_np_array": {"a": np.array([1, 2, 3])},
        "df": pd.DataFrame({"col1": [1, 2], "col2": [3, 4]}),
    }
    return data


def test_infer_datatype():
    assert infer_datatype(1) is None
    assert infer_datatype(1.0) is None
    assert infer_datatype("1") is None
    assert infer_datatype(True) is None
    assert infer_datatype(b"1") is None

    assert infer_datatype(np.array([1, 2, 3])).identifier == "numpy.int64[3]"
    assert infer_datatype(torch.tensor([1, 2, 3])).identifier == "torch.int64[3]"

    assert infer_datatype({"a": 1}) is None
    assert infer_datatype({"a": 1}, ibis=True).identifier == "json"

    assert infer_datatype({"a": np.array([1, 2, 3])}).identifier == "dill_base"

    assert (
        infer_datatype(pd.DataFrame({"col1": [1, 2], "col2": [3, 4]})).identifier
        == "dill_base"
    )


def test_infer_schema_mongo(data):
    schema = infer_schema(data)
    encode_data = schema(data)

    expected_datatypes = [
        "np_array",
        "torch_tensor",
        "dict_np_array",
        "df",
    ]
    assert sorted(schema.encoded_types) == sorted(expected_datatypes)
    for key in expected_datatypes:
        if schema.fields.get(key) is not None:
            assert str(data[key]) != str(encode_data[key])

    decode_data = Document(schema.decode_data(encode_data)).unpack()
    for key in data:
        assert isinstance(data[key], type(decode_data[key]))
        assert str(data[key]) == str(decode_data[key])


def test_infer_schema_ibis(data):
    schema = infer_schema(data, ibis=True)
    encode_data = schema(data)

    expected_datatypes = [
        "np_array",
        "torch_tensor",
        "dict",
        "dict_np_array",
        "df",
    ]
    assert sorted(schema.encoded_types) == sorted(expected_datatypes)
    for key in expected_datatypes:
        if schema.fields.get(key) is not None:
            assert str(data[key]) != str(encode_data[key])

    decode_data = Document(schema.decode_data(encode_data)).unpack()
    for key in data:
        assert isinstance(data[key], type(decode_data[key]))
        assert str(data[key]) == str(decode_data[key])


@pytest.mark.parametrize("db", [DBConfig.mongodb_empty], indirect=True)
def test_mongo_schema(db, data):
    collection_name = "documents"
    schema = Collection.infer_schema(data)

    db.apply(schema)

    db.execute(
        Collection(collection_name).insert_one(
            Document(data), schema=schema.identifier
        ),
    )
    collection = Collection(collection_name)
    decode_data = collection.find_one().execute(db).unpack()
    for key in data:
        assert isinstance(data[key], type(decode_data[key]))
        assert str(data[key]) == str(decode_data[key])


@pytest.mark.parametrize("db", [DBConfig.sqldb_empty], indirect=True)
def test_ibis_schema(db, data):
    data["id"] = str("1")
    schema = Table.infer_schema(data)

    t = Table(identifier="my_table", schema=schema)

    db.apply(t)

    db.execute(t.insert([Document(data)]))

    select = t.select(*data.keys()).limit(1)
    decode_data = db.execute(select).next().unpack()
    for key in data:
        assert isinstance(data[key], type(decode_data[key]))
        assert str(data[key]) == str(decode_data[key])