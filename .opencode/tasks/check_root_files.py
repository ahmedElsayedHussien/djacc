import os, re, py_compile

files = [
    'manage.py',
    'check_views.py',
    'config/urls.py',
    'config/wsgi.py',
    'config/asgi.py',
]

for path in files:
    full = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), path)
    if not os.path.exists(full):
        print(f'MISSING: {path}')
        continue
    try:
        py_compile.compile(full, doraise=True)
        print(f'OK: {path}')
    except py_compile.PyCompileError as e:
        print(f'SYNTAX ERROR: {path}: {e}')

for path in files:
    full = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), path)
    if not os.path.exists(full):
        continue
    with open(full, encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    for i, line in enumerate(lines, 1):
        if re.match(r'^\s+except\s*:', line):
            print(f'BARE EXCEPT: {path}:{i}')
        if re.match(r'^\s+(import\s|from\s)', line) and line.startswith((' ', '\t')):
            print(f'INLINE IMPORT: {path}:{i}: {line.rstrip()}')
