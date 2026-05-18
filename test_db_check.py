"""Unit tests for db_check module."""
import os
import unittest
from unittest.mock import MagicMock, patch, call
from db_check import _clean_invoice_number, check_invoices, _get_connection, _candidate_queries


class TestCleanInvoiceNumber(unittest.TestCase):
    """Tests for invoice number cleaning function."""

    def test_clean_simple(self):
        """Test basic cleaning of invoice numbers."""
        self.assertEqual(_clean_invoice_number("INV-123"), "INV123")
        self.assertEqual(_clean_invoice_number("INV_456"), "INV456")
        self.assertEqual(_clean_invoice_number("INV 789"), "INV789")

    def test_clean_special_chars(self):
        """Test cleaning with special characters."""
        self.assertEqual(_clean_invoice_number("INV/2026-0518"), "INV20260518")
        self.assertEqual(_clean_invoice_number("INV#001"), "INV001")
        self.assertEqual(_clean_invoice_number("INV.2026.0001"), "INV20260001")

    def test_clean_already_clean(self):
        """Test with already-clean invoice numbers."""
        self.assertEqual(_clean_invoice_number("INV123"), "INV123")
        self.assertEqual(_clean_invoice_number("123"), "123")

    def test_clean_uppercase(self):
        """Test that result is uppercase."""
        self.assertEqual(_clean_invoice_number("inv-123"), "INV123")
        self.assertEqual(_clean_invoice_number("abc-xyz"), "ABCXYZ")

    def test_clean_none_input(self):
        """Test with None input."""
        self.assertEqual(_clean_invoice_number(None), "")

    def test_clean_empty_string(self):
        """Test with empty string."""
        self.assertEqual(_clean_invoice_number(""), "")


class TestCandidateQueries(unittest.TestCase):
    """Tests for SQL query fallback list."""

    def test_default_queries(self):
        """Test that default queries are returned when env var not set."""
        with patch.dict(os.environ, {}, clear=False):
            if "DB_EXISTING_INVOICE_SQL" in os.environ:
                del os.environ["DB_EXISTING_INVOICE_SQL"]
            queries = _candidate_queries()
            self.assertIsInstance(queries, list)
            self.assertGreater(len(queries), 0)

    def test_env_query_override(self):
        """Test that env var overrides default queries."""
        custom_q = "SELECT id FROM my_table WHERE inv = ?"
        with patch.dict(os.environ, {"DB_EXISTING_INVOICE_SQL": custom_q}):
            queries = _candidate_queries()
            self.assertEqual(queries, [custom_q])


class TestGetConnection(unittest.TestCase):
    """Tests for database connection setup."""

    def test_no_config(self):
        """Test that None is returned when no config provided."""
        with patch.dict(os.environ, {"DB_HOST": "", "DB_CONNECTION_STRING": ""}, clear=False):
            # Remove these if they exist
            os.environ.pop("DB_HOST", None)
            os.environ.pop("DB_CONNECTION_STRING", None)
            with patch("db_check.pyodbc") as mock_pyodbc:
                mock_pyodbc.connect.side_effect = Exception("Should not be called")
                conn = _get_connection()
                self.assertIsNone(conn)

    def test_connection_string_env(self):
        """Test that DB_CONNECTION_STRING is used when provided."""
        conn_str = "DRIVER={ODBC};SERVER=test"
        with patch.dict(os.environ, {"DB_CONNECTION_STRING": conn_str}):
            with patch("db_check.pyodbc") as mock_pyodbc:
                mock_conn = MagicMock()
                mock_pyodbc.connect.return_value = mock_conn
                conn = _get_connection()
                mock_pyodbc.connect.assert_called_once_with(conn_str, autocommit=True)
                self.assertEqual(conn, mock_conn)

    def test_host_fallback(self):
        """Test that DB_HOST is used when DB_CONNECTION_STRING is not provided."""
        with patch.dict(os.environ, {"DB_HOST": "localhost", "DB_CONNECTION_STRING": ""}, clear=False):
            os.environ.pop("DB_CONNECTION_STRING", None)
            with patch("db_check.pyodbc") as mock_pyodbc:
                mock_conn = MagicMock()
                mock_pyodbc.connect.return_value = mock_conn
                conn = _get_connection()
                # Check that the connection was attempted
                self.assertEqual(conn, mock_conn)
                # Verify pyodbc.connect was called (with any args)
                self.assertTrue(mock_pyodbc.connect.called)


class TestCheckInvoices(unittest.TestCase):
    """Tests for the main check_invoices function."""

    def test_empty_batch(self):
        """Test with empty batch returns empty list."""
        result = check_invoices([])
        self.assertEqual(result, [])

    def test_no_connection_available(self):
        """Test graceful degradation when no DB connection."""
        with patch("db_check._get_connection", return_value=None):
            pairs = [("Vendor A", "INV001"), ("Vendor B", "INV002")]
            result = check_invoices(pairs)
            self.assertEqual(len(result), 2)
            for r in result:
                self.assertFalse(r.get("exists"))
                self.assertIsNone(r.get("db_vendor"))

    def test_cursor_error_graceful(self):
        """Test graceful handling of cursor creation error."""
        mock_conn = MagicMock()
        mock_conn.cursor.side_effect = Exception("Cursor error")
        with patch("db_check._get_connection", return_value=mock_conn):
            pairs = [("Vendor A", "INV001")]
            result = check_invoices(pairs)
            self.assertEqual(len(result), 1)
            self.assertFalse(result[0].get("exists"))

    def test_invoice_found(self):
        """Test successful invoice lookup."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("Vendor Name",)
        mock_conn.cursor.return_value = mock_cursor
        
        with patch("db_check._get_connection", return_value=mock_conn):
            with patch("db_check._candidate_queries", return_value=["SELECT vendor FROM invoices WHERE invoice_number = ?"]):
                pairs = [("Vendor A", "INV001")]
                result = check_invoices(pairs)
                self.assertEqual(len(result), 1)
                self.assertTrue(result[0].get("exists"))
                self.assertEqual(result[0].get("db_vendor"), "Vendor Name")

    def test_invoice_not_found(self):
        """Test when invoice does not exist."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        
        with patch("db_check._get_connection", return_value=mock_conn):
            with patch("db_check._candidate_queries", return_value=["SELECT vendor FROM invoices WHERE invoice_number = ?"]):
                pairs = [("Vendor A", "INV001")]
                result = check_invoices(pairs)
                self.assertEqual(len(result), 1)
                self.assertFalse(result[0].get("exists"))

    def test_permission_error_handled(self):
        """Test that permission errors are handled gracefully."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("permission denied")
        mock_conn.cursor.return_value = mock_cursor
        
        with patch("db_check._get_connection", return_value=mock_conn):
            with patch("db_check._candidate_queries", return_value=["SELECT vendor FROM invoices WHERE invoice_number = ?"]):
                pairs = [("Vendor A", "INV001")]
                result = check_invoices(pairs)
                self.assertEqual(len(result), 1)
                self.assertFalse(result[0].get("exists"))

    def test_batch_multiple_invoices(self):
        """Test checking multiple invoices in one batch."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Mock fetchone to return based on call count
        # Call 0: INV001 exact → found
        # Call 1: INV002 exact → not found
        # Call 2: INV002 cleaned → not found
        call_count = [0]
        
        def mock_fetchone():
            result = None
            if call_count[0] == 0:
                result = ("ABC Corp",)  # first invoice found
            # else: all other calls return None
            call_count[0] += 1
            return result
        
        mock_cursor.fetchone.side_effect = mock_fetchone
        mock_conn.cursor.return_value = mock_cursor
        
        with patch("db_check._get_connection", return_value=mock_conn):
            with patch("db_check._candidate_queries", return_value=["SELECT vendor FROM invoices WHERE invoice_number = ?"]):
                pairs = [("ABC Corp", "INV001"), ("XYZ Inc", "INV002")]
                result = check_invoices(pairs)
                self.assertEqual(len(result), 2)
                self.assertTrue(result[0].get("exists"))
                self.assertFalse(result[1].get("exists"))


if __name__ == "__main__":
    unittest.main()
