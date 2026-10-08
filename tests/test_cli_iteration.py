from stoms.cli import _iteration_label


def test_iteration_label_handles_absent_malformed_and_duplicate_tags() -> None:
    assert _iteration_label(()) == "-"
    assert _iteration_label(("iteration:000",)) == "iteration:000"
    assert _iteration_label(("iteration:",)) == "-"
    assert _iteration_label(("iteration:001", "iteration:002")) == "-"
