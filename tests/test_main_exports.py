from __future__ import annotations

import main


def test_main_reexports_pipeline_callbacks():
    assert callable(main.on_card_back)
    assert callable(main.on_card_forward)
