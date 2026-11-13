import pytest

from knit_copilot import kb


def test_kb_loads_and_aliases_are_unambiguous():
    abbrs = kb.abbreviations()
    assert len(abbrs) >= 60
    kb.alias_index()  # raises on ambiguous aliases


@pytest.mark.parametrize("op,consumes,produces", [
    ("k", 1, 1), ("k2tog", 2, 1), ("ssk", 2, 1), ("yo", 0, 1), ("m1l", 0, 1), ("kfb", 1, 2),
    ("s2kp", 3, 1), ("sk2p", 3, 1), ("k3tog", 3, 1), ("c4f", 4, 4), ("t3b", 3, 3), ("yo2", 0, 2),
    ("bo", 1, 0), ("co", 0, 1), ("drop", 1, 0), ("pm", 0, 0),
])
def test_stitch_arithmetic(op, consumes, produces):
    a = kb.stitch_op(op)
    assert (a.consumes, a.produces) == (consumes, produces)


@pytest.mark.parametrize("text,expected", [
    ("K2tog", "k2tog"), ("k2 tog", "k2tog"), ("SSK", "ssk"), ("sl1 k1 psso", "skp"), ("cdd", "s2kp"),
    ("2/2 LC", "c4f"), ("yfwd", "yo"), ("cast off", "bo"), ("M1", "m1l"), ("k1 tbl", "k_tbl"),
    ("kf&b", "kfb"), ("stocking stitch", "st_st"), ("tension", "gauge_term"), ("sl1", "sl_pw"),
])
def test_lookup_aliases(text, expected):
    assert kb.lookup(text).id == expected


def test_unknown_and_term_lookups():
    assert kb.lookup("zz9tog") is None
    assert kb.lookup("RS").category == "term"
    with pytest.raises(KeyError):
        kb.stitch_op("RS")


def test_every_stitch_op_has_chart_symbol_and_description():
    for a in kb.abbreviations().values():
        assert a.description
        if a.is_stitch_op and a.category != "marker":
            assert a.chart_symbol is not None and a.chart_symbol_ws is not None, a.id


def test_yarn_weights_cover_ravelry_names_once():
    names = [n for c in kb.yarn_weights()["categories"] for n in c["ravelry_names"]]
    assert len(names) == len(set(names))
    assert {"Sport", "DK", "Worsted", "Aran", "Fingering", "Bulky", "Super Bulky"} <= set(names)
    for c in kb.yarn_weights()["categories"]:
        assert c["needle_mm"][0] < c["needle_mm"][1]


def test_fibres_have_required_fields_and_unique_aliases():
    required = {"aliases", "elasticity", "warmth", "drape", "needle_adjust_mm", "care", "blocking", "tips"}
    aliases = []
    for name, f in kb.fibres().items():
        assert required <= set(f), name
        aliases += [a.lower() for a in f["aliases"]]
    assert len(aliases) == len(set(aliases))
