from latency_report import percentile, summarize


SAMPLES = [8.0, 10.0, 12.0, 20.0, 50.0]


def test_median():
    assert percentile(SAMPLES, 50) == 12.0


def test_p95():
    assert percentile(SAMPLES, 95) == 50.0


def test_p99():
    assert percentile(SAMPLES, 99) == 50.0


def test_summary():
    assert summarize(SAMPLES) == {"p50": 12.0, "p95": 50.0, "p99": 50.0}


def test_does_not_mutate_input():
    values = [3.0, 1.0, 2.0]
    percentile(values, 50)
    assert values == [3.0, 1.0, 2.0]
