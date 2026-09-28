import ast
import re
from pathlib import Path

from peto_agent import commands, __main__ as cli
from peto_agent.catalog import commands as catalog


def test_command_registry_and_dispatch_have_documentation():
    entries = catalog()
    names = {item['name'] for item in entries}
    assert len(names) == len(entries)
    assert names == {command.name for command in commands.COMMANDS}
    for entry in entries:
        assert all(entry.get(key) for key in ('name', 'description', 'usage', 'details', 'since'))
    tree = ast.parse(Path(cli.__file__).read_text(encoding='utf-8'))
    literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
                and isinstance(node.value, str) and re.fullmatch(r'/[a-z]+', node.value)}
    assert literals <= names | {'/exit', '/quit'}
