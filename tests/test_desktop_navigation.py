"""Run the native navigation check outside pytest's multithreaded process."""

import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.offline


def test_initial_chat_and_sidebar_modes_with_saved_history():
    probe = Path(__file__).with_name('desktop_navigation_probe.py')
    result = subprocess.run([sys.executable, str(probe)], capture_output=True, text=True,
                            timeout=15)
    if result.returncode == 77:
        pytest.skip('No graphical display is available')
    assert result.returncode == 0, result.stdout + result.stderr
