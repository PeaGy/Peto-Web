"""Command documentation shipped with the same CLI build as /help."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def commands():
    return json.loads(Path(__file__).with_name('command_catalog.json').read_text(encoding='utf-8'))['commands']
