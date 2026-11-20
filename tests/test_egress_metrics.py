import unittest
from unittest.mock import Mock, patch

from shared.egress_metrics import _endpoint_label, supabase_get


class EgressMetricsTests(unittest.TestCase):
    def test_endpoint_label_does_not_include_query_parameters(self):
        self.assertEqual(
            _endpoint_label("https://example.supabase.co/rest/v1/alinhamentos?select=*&token=secret"),
            "alinhamentos",
        )

    def test_non_postgrest_url_has_generic_label(self):
        self.assertEqual(_endpoint_label("https://example.com/api"), "non_postgrest")

    @patch("shared.egress_metrics.requests.get")
    def test_get_returns_original_response_and_logs_metadata_only(self, get_mock):
        response = Mock()
        response.content = b'[{"id":1},{"id":2}]'
        response.status_code = 200
        response.json.return_value = [{"id": 1}, {"id": 2}]
        get_mock.return_value = response

        with self.assertLogs("sia.egress", level="INFO") as captured:
            result = supabase_get(
                "https://example.supabase.co/rest/v1/alinhamentos?select=*",
                operation="load_alignment_rows",
                headers={"Authorization": "Bearer do-not-log"},
            )

        self.assertIs(result, response)
        get_mock.assert_called_once()
        log_text = "\n".join(captured.output)
        self.assertIn("operation=load_alignment_rows", log_text)
        self.assertIn("endpoint=alinhamentos", log_text)
        self.assertIn("bytes_body=", log_text)
        self.assertIn("rows=2", log_text)
        self.assertNotIn("do-not-log", log_text)
        self.assertNotIn("select=*", log_text)


if __name__ == "__main__":
    unittest.main()
