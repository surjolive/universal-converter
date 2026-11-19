from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

@dataclass
class ConversionResult:
    output_path: Path
    engine: str
    metadata: dict

class ConverterRegistry:
    def __init__(self):
        self._routes = {}

    def register(self, source: str, target: str, engine: str, converter: Callable):
        self._routes[(source.lower(), target.lower())] = (engine, converter)

    def get(self, source: str, target: str):
        return self._routes.get((source.lower(), target.lower()))

    def supported_sources(self):
        return sorted({source for source, _ in self._routes})

    def supported_targets(self, source: Optional[str] = None):
        if source:
            return sorted(target for src, target in self._routes if src == source.lower())
        return sorted({target for _, target in self._routes})

    def formats(self):
        return {
            "routes": [
                {"source": source, "target": target, "engine": engine}
                for (source, target), (engine, _) in sorted(self._routes.items())
            ],
            "sources": self.supported_sources(),
        }
