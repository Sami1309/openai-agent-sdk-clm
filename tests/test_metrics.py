"""Usage alignment at failed requests and boundaries between SDK runs."""

from types import SimpleNamespace

from agents_clm import ContextTrace


def usage(*inputs):
    return SimpleNamespace(request_usage_entries=[
        SimpleNamespace(input_tokens=n, output_tokens=n // 10,
                        input_tokens_details=SimpleNamespace(cached_tokens=0),
                        output_tokens_details=SimpleNamespace(reasoning_tokens=0))
        for n in inputs
    ])


def test_usage_is_attached_to_completed_calls_before_failed_request():
    trace = ContextTrace()
    trace.record("sys", [{"role": "user", "content": "first"}])
    trace.attach_usage(usage(100))
    trace.begin_run()
    trace.record("sys", [{"role": "user", "content": "second"}])
    trace.record("sys", [{"role": "user", "content": "failed"}])
    trace.attach_usage(usage(200))
    assert trace.steps[0]["api_input_tokens"] == 100
    assert trace.steps[1]["api_input_tokens"] == 200
    assert "api_input_tokens" not in trace.steps[2]
    assert trace.summary()["api_input_tokens"] == 300


def test_rejected_request_does_not_prime_prefix_reuse():
    trace = ContextTrace()
    items = [{"role": "user", "content": "task"}]
    trace.record("sys", items)
    trace.reject_last("over_budget")
    trace.record("sys", items)
    assert trace.steps[-1]["reused"] == 0
    assert trace.summary()["model_calls"] == 1


def test_final_snapshot_does_not_prime_reuse_or_replace_last_sent_text():
    trace = ContextTrace()
    trace.record("sys", [{"role": "user", "content": "sent"}])
    trace.record("sys", [{"role": "user", "content": "unsent"}], kind="final")
    assert "unsent" not in trace.last_sent_text
    trace.record("sys", [{"role": "user", "content": "unsent"}])
    assert trace.steps[-1]["reused"] == trace.steps[-1]["messages"][0]["tokens"]


def test_failure_before_first_request_cannot_reject_previous_run():
    trace = ContextTrace()
    trace.record("sys", [{"role": "user", "content": "completed"}])
    trace.begin_run()
    assert not trace.reject_last("over_budget")
    assert trace.summary()["model_calls"] == 1
