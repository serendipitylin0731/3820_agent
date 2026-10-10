"""Check that long answers scroll with the conversation, not inside a card."""

import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.offline


def test_answer_card_grows_with_wrapped_content_and_window_resize():
    probe = Path(__file__).with_name('desktop_layout_probe.py')
    result = subprocess.run([sys.executable, str(probe)], capture_output=True, text=True,
                            timeout=15)
    if result.returncode == 77:
        pytest.skip('No graphical display is available')
    assert result.returncode == 0, result.stdout + result.stderr
