"""Exit 0 if src/inventory/export.py exists and defines at least one function."""
import ast
import os
import sys

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "inventory", "export.py")
try:
    tree = ast.parse(open(path).read())
except (OSError, SyntaxError) as exc:
    print("FAIL export.py:", exc)
    sys.exit(1)
if not any(isinstance(n, ast.FunctionDef) for n in ast.walk(tree)):
    print("FAIL export.py defines no function")
    sys.exit(1)
print("ok   export.py defines a function")
