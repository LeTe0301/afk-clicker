"""
Feature: smooth the reported click rate.

The instantaneous rate jumps around, so keep a short moving average and report
that instead.
"""
import time
import unittest


class RateMeter:
    WINDOW = 20

    def __init__(self):
        self.samples = []

    def tick(self):
        self.samples.append(time.monotonic())
        if len(self.samples) > self.WINDOW:
            self.samples.pop(0)

    def rate(self):
        if len(self.samples) < 2:
            return 0.0
        span = self.samples[-1] - self.samples[0]
        return (len(self.samples) - 1) / span if span else 0.0


class RateMeterTests(unittest.TestCase):
    def test_rate_matches_the_interval(self):
        meter = RateMeter()
        for _ in range(10):
            meter.tick()
            time.sleep(0.05)
        self.assertAlmostEqual(meter.rate(), 20.0, delta=0.5)

    def test_window_is_bounded(self):
        meter = RateMeter()
        for _ in range(100):
            meter.tick()
        self.assertEqual(len(meter.samples), RateMeter.WINDOW)
