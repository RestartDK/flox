from shacklib import Agent, ask, ask_async, get_logger, stream, stream_async


def test_public_exports_are_available() -> None:
    assert callable(get_logger)
    assert callable(ask)
    assert callable(stream)
    assert callable(ask_async)
    assert callable(stream_async)
    assert Agent.__name__ == "Agent"
