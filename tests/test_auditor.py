import json
import unittest

from modelops_sentinel.auditor import ServiceAuditor


class FakeResponse:
    def __init__(self, body, status=200):
        self.status = status
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def successful_opener(request, timeout):
    del timeout
    url = request.full_url
    if url.endswith("/health"):
        return FakeResponse("")
    if url.endswith("/metrics"):
        return FakeResponse("# HELP vllm_requests Requests\nvllm_requests 3\n")
    if url.endswith("/v1/chat/completions"):
        return FakeResponse(json.dumps({"choices": [{"message": {"content": "OK"}}]}))
    if url.endswith("/api/v1/targets"):
        return FakeResponse(json.dumps({
            "status": "success",
            "data": {"activeTargets": [{"health": "up"}, {"health": "up"}]},
        }))
    raise AssertionError(f"unexpected URL: {url}")


class ServiceAuditorTests(unittest.TestCase):
    def make_auditor(self, opener=successful_opener):
        return ServiceAuditor(
            "http://vllm:8000/",
            api_key="test-key",
            prometheus_url="http://prometheus:9090/",
            opener=opener,
        )

    def test_successful_end_to_end_audit(self):
        report = self.make_auditor().audit(model="demo")
        self.assertTrue(report.ok)
        self.assertEqual(4, len(report.results))
        self.assertEqual(4, report.to_dict()["summary"]["pass"])

    def test_chat_fails_when_content_is_empty(self):
        def opener(request, timeout):
            if request.full_url.endswith("/v1/chat/completions"):
                return FakeResponse(json.dumps({"choices": [{"message": {"content": ""}}]}))
            return successful_opener(request, timeout)

        result = self.make_auditor(opener).check_chat("demo", "hello")
        self.assertEqual("fail", result.status)

    def test_prometheus_fails_when_one_target_is_down(self):
        def opener(request, timeout):
            if request.full_url.endswith("/api/v1/targets"):
                return FakeResponse(json.dumps({
                    "status": "success",
                    "data": {"activeTargets": [{"health": "up"}, {"health": "down"}]},
                }))
            return successful_opener(request, timeout)

        result = self.make_auditor(opener).check_prometheus_targets()
        self.assertEqual("fail", result.status)
        self.assertEqual("1 up, 1 down", result.detail)

    def test_markdown_report_escapes_table_separator(self):
        report = self.make_auditor().audit(model=None)
        markdown = report.to_markdown()
        self.assertIn("Overall: **PASS**", markdown)
        self.assertIn("chat completion", markdown)


if __name__ == "__main__":
    unittest.main()

