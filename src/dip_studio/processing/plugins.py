"""Versioned plugin capability contract; discovery is an infrastructure concern."""

from typing import Protocol

from dip_studio.processing.contracts import Processor


class ProcessorPlugin(Protocol):
    plugin_id: str
    api_version: int

    def processors(self) -> tuple[Processor[object, object], ...]: ...
