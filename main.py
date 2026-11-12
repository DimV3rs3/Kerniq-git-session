"""Ships with Kerniq. The engine does the git work. This file only declares the plugin."""

from __future__ import annotations

from Kerniq.plugins.base import Plugin
from Kerniq.plugins.manifest import PluginManifest


class PluginImpl(Plugin):
    def __init__(self) -> None:
        self._manifest = PluginManifest(
            plugin_id="plugin_git_session",
            name="Git session",
            version="0.1.0",
            api_version="1.0",
            manifest_version="1.0",
            entry_point="main.PluginImpl",
            description=(
                "Commits workspace changes at the end of a run and can roll back "
                "one file or the whole session."
            ),
            capabilities=["tools"],
            author="Kerniq",
            license="MIT",
        )

    @property
    def manifest(self) -> PluginManifest:
        return self._manifest

    async def initialize(self, context) -> bool:
        return True

    async def shutdown(self) -> None:
        return None
