import unittest

import numpy as np

from audio_core import analyze_bpm_samples


SAMPLE_RATE = 22050


def click_track(parts: tuple[tuple[float, float], ...]) -> np.ndarray:
    duration_seconds = sum(duration for _bpm, duration in parts)
    samples = np.zeros(int(duration_seconds * SAMPLE_RATE), dtype=np.float32)
    pulse = np.hanning(int(SAMPLE_RATE * 0.025)).astype(np.float32)
    offset = 0.0
    for bpm, duration in parts:
        for timestamp in np.arange(offset + 0.3, offset + duration - 0.1, 60.0 / bpm):
            start = int(timestamp * SAMPLE_RATE)
            end = min(len(samples), start + len(pulse))
            samples[start:end] += pulse[: end - start]
        offset += duration
    return samples


class BpmAnalysisTests(unittest.TestCase):
    def test_fixed_tempo_uses_timestamp_regression(self) -> None:
        result = analyze_bpm_samples(click_track(((128.0, 42.0),)), SAMPLE_RATE)

        self.assertAlmostEqual(result["bpm"], 128.0, delta=0.7)
        self.assertAlmostEqual(result["averageBpm"], 128.0, delta=0.7)
        self.assertFalse(result["isVariableTempo"])
        self.assertGreaterEqual(result["confidence"], 65)
        self.assertGreater(result["beatCount"], 60)
        self.assertEqual(result["segments"][0]["startMs"], result["activeStartMs"])
        self.assertEqual(result["segments"][-1]["endMs"], result["analysisEndMs"])

    def test_double_time_is_normalized_to_primary_beat_layer(self) -> None:
        result = analyze_bpm_samples(click_track(((240.0, 42.0),)), SAMPLE_RATE)

        self.assertAlmostEqual(result["bpm"], 120.0, delta=0.8)
        self.assertTrue(any(item["label"] == "倍速候选" for item in result["candidates"]))

    def test_tempo_change_keeps_local_sections(self) -> None:
        result = analyze_bpm_samples(click_track(((120.0, 35.0), (150.0, 35.0))), SAMPLE_RATE)
        section_bpms = [section["bpm"] for section in result["segments"]]

        self.assertTrue(result["isVariableTempo"])
        self.assertTrue(any(abs(value - 120.0) < 1.0 for value in section_bpms))
        self.assertTrue(any(abs(value - 150.0) < 1.0 for value in section_bpms))
        for left, right in zip(result["segments"], result["segments"][1:]):
            self.assertEqual(left["endMs"], right["startMs"])
        durations = [section["endMs"] - section["startMs"] for section in result["segments"]]
        expected_average = sum(
            section["bpm"] * duration for section, duration in zip(result["segments"], durations)
        ) / sum(durations)
        self.assertAlmostEqual(result["averageBpm"], expected_average, places=2)
        self.assertAlmostEqual(result["minimumBpm"], min(section_bpms), places=2)
        self.assertAlmostEqual(result["maximumBpm"], max(section_bpms), places=2)

    def test_short_audio_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            analyze_bpm_samples(np.zeros(SAMPLE_RATE * 2, dtype=np.float32), SAMPLE_RATE)


if __name__ == "__main__":
    unittest.main()
