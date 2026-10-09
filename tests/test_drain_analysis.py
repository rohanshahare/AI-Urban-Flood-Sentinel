import io
import json
import struct
import unittest
from unittest.mock import patch

from vision.drain_analysis import (
    VisionInputError,
    VisionServiceError,
    analyze_drain,
)


def tiny_png_bytes():
    """Return a tiny PNG-signature payload; decoding is mocked in these unit tests."""
    # PNG header is sufficient for input-type validation when the API is mocked.
    # Real image decoding is delegated to the configured Ollama vision model.
    return b"\x89PNG\r\n\x1a\n" + b"mock-test-image-payload"


def valid_model_result(**overrides):
    result = {
        "drain_visible": True,
        "image_quality": "good",
        "blockage_detected": True,
        "blockage_percentage": 35,
        "assessment_uncertain": False,
        "observations": "Leaves visibly cover part of the drain opening.",
        "warnings": [],
    }
    result.update(overrides)
    return result


class DrainAnalysisTests(unittest.TestCase):
    @patch("vision.drain_analysis._call_ollama")
    def test_valid_bytes_return_contract(self, mock_call):
        mock_call.return_value = valid_model_result()
        result = analyze_drain(tiny_png_bytes(), drain_id="D-1", location={"lat": 12.9, "lon": 77.5})
        self.assertEqual(result["drain_id"], "D-1")
        self.assertTrue(result["blockage_detected"])
        self.assertEqual(result["blockage_percentage"], 35.0)
        self.assertIsNone(result["confidence"])
        self.assertEqual(result["location"], {"lat": 12.9, "lon": 77.5})
        self.assertTrue(result["timestamp"].endswith("Z"))
        self.assertIsInstance(result["warnings"], list)
        mock_call.assert_called_once()

    def test_empty_image_is_rejected(self):
        with self.assertRaisesRegex(VisionInputError, "empty"):
            analyze_drain(b"")

    def test_unrecognized_image_is_rejected(self):
        with self.assertRaisesRegex(VisionInputError, "Unsupported"):
            analyze_drain(b"not an image")

    def test_missing_file_is_reported(self):
        with self.assertRaises(VisionInputError):
            analyze_drain("path-that-does-not-exist.png")

    def test_binary_file_object_is_accepted(self):
        with patch("vision.drain_analysis._call_ollama", return_value=valid_model_result(blockage_detected=False, blockage_percentage=None)):
            result = analyze_drain(io.BytesIO(tiny_png_bytes()))
        self.assertFalse(result["blockage_detected"])
        self.assertIsNone(result["blockage_percentage"])

    def test_uncertain_assessment_cannot_be_positive(self):
        model_result = valid_model_result(assessment_uncertain=True, blockage_percentage=70, warnings=["Poor visibility."])
        with patch("vision.drain_analysis._call_ollama", return_value=model_result):
            result = analyze_drain(tiny_png_bytes())
        self.assertFalse(result["blockage_detected"])
        self.assertIsNone(result["blockage_percentage"])
        self.assertTrue(any("uncertain" in warning.lower() for warning in result["warnings"]))

    def test_no_visible_drain_cannot_be_positive(self):
        with patch("vision.drain_analysis._call_ollama", return_value=valid_model_result(drain_visible=False)):
            result = analyze_drain(tiny_png_bytes())
        self.assertFalse(result["blockage_detected"])
        self.assertIsNone(result["blockage_percentage"])

    def test_invalid_metadata_is_rejected(self):
        with self.assertRaisesRegex(VisionInputError, "location"):
            analyze_drain(tiny_png_bytes(), location={"lat": 999, "lon": 77.0})

    def test_invalid_model_percentage_is_rejected(self):
        with patch("vision.drain_analysis._call_ollama", return_value=valid_model_result(blockage_percentage=140)):
            with self.assertRaises(VisionServiceError):
                analyze_drain(tiny_png_bytes())

    def test_service_failure_propagates_clear_error(self):
        with patch("vision.drain_analysis._call_ollama", side_effect=VisionServiceError("Ollama unavailable")):
            with self.assertRaisesRegex(VisionServiceError, "unavailable"):
                analyze_drain(tiny_png_bytes())

    def test_non_positive_timeout_is_rejected(self):
        with self.assertRaisesRegex(VisionInputError, "timeout"):
            analyze_drain(tiny_png_bytes(), timeout=0)


if __name__ == "__main__":
    unittest.main()
