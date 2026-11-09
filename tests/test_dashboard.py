from dashboard.__main__ import trace_path


def test_trace_path_only_serves_files_directly_in_a_run(tmp_path):
    runs = tmp_path / "runs"
    (runs / "run1").mkdir(parents=True)
    (runs / "run1" / "trace.json").write_text("{}")
    (tmp_path / "secret.txt").write_text("x")
    assert trace_path("run1", "trace.json", runs) == (runs / "run1" / "trace.json").resolve()
    assert trace_path("..", "secret.txt", runs) is None
    assert trace_path(".", "run1", runs) is None
    assert trace_path("run1", "../../secret.txt", runs) is None
    assert trace_path("run1", "missing.json", runs) is None
