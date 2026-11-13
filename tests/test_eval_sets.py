"""The hand-written eval sources must always pass the label validation in build_eval_sets."""
from knit_copilot.data import build_eval_sets as b


def test_all_eval_sources_validate():
    rows = b._yarn_rows()
    sets = [b.build_intents(), b.build_setup(), b.build_kb(), b.build_yarn_links(rows), b.build_yarn_advice(rows)]
    assert all(sets)
    for cases in sets:
        assert {c["split"] for c in cases} == {"dev", "test"}


def test_setup_state_is_computed_in_metric():
    by_ref = {c["case_ref"]: c for c in b.build_setup()}
    assert by_ref["s06"]["expected"]["state"] == {"gauge_sts_10cm": 17.7, "gauge_rows_10cm": 23.6, "needle_mm": 5.0}
    assert by_ref["s14"]["expected"]["state"] == {}          # locked project: nothing changes
