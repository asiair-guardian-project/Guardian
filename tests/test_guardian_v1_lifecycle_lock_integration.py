import ast
from pathlib import Path


def test_monitor_lock_surrounds_runner():
    tree = ast.parse(Path('guardian_v1.py').read_text())
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main']
    assert len(functions) == 1
    with_nodes = [n for n in ast.walk(functions[0]) if isinstance(n, ast.With)]
    guarded = [n for n in with_nodes if any(isinstance(item.context_expr, ast.Call) and
               isinstance(item.context_expr.func, ast.Name) and
               item.context_expr.func.id == 'monitor_lifetime_lock' for item in n.items)]
    assert len(guarded) == 1
    assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and
               n.func.attr == 'run' and isinstance(n.func.value, ast.Name) and
               n.func.value.id == 'runner' for n in ast.walk(guarded[0]))


def test_identity_binding_preserved():
    tree = ast.parse(Path('guardian_v1.py').read_text())
    assert any(isinstance(n, ast.keyword) and n.arg == 'configuration_fingerprint' and
               isinstance(n.value, ast.Name) and n.value.id == 'installation_identity'
               for n in ast.walk(tree))
