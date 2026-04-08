import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from temperature import calculate_wire_temp

def test_copper_low_load():
    # copper (300.0) * 10% load (0.10) = 30.0
    assert calculate_wire_temp("copper", 10) == 30.0

def test_aluminum_high_load():
    # aluminum (200.0) * 70% load (0.70) = 140.0
    assert calculate_wire_temp("aluminum", 70) == 140.0

def test_fiber_medium_load():
    # fiber (50.0) * 30% load (0.30) = 15.0
    assert calculate_wire_temp("fiber", 30) == 15.0

def test_copper_critical_load():
    # copper (300.0) * 90% load (0.90) = 270.0
    assert calculate_wire_temp("copper", 90) == 270.0
