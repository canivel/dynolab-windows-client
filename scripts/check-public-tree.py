"""Small supplemental source hygiene check; not a complete secret scanner."""
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
result = subprocess.run(['git', 'ls-files', '-z'], cwd=root, capture_output=True, check=True)
paths = [root / p.decode() for p in result.stdout.split(b'\0') if p]
patterns = [
    re.compile(r'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----'),
    re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    re.compile(r'[A-Z]:[\\/]Users[\\/][^\s\x22]+'),
    re.compile(r'/Users/[a-zA-Z][^/\s]+/'),
]
errors = []
for path in paths:
    relative = path.relative_to(root).as_posix()
    if any(part in ('.dyno', '.ssh', 'dist', 'work', '__pycache__') for part in path.relative_to(root).parts) or path.suffix.lower() in ('.pfx', '.p12', '.pem', '.key', '.exe', '.dll', '.zip', '.gguf', '.safetensors', '.log') or path.name.startswith('.env'):
        errors.append(relative + ': excluded artifact')
        continue
    text = path.read_text(encoding='utf-8')
    # This test deliberately includes a rejected private-key header, not a key.
    if relative == 'tests/test_worker.py':
        text = text.replace('-----BEGIN ' + 'OPENSSH PRIVATE KEY-----', '[rejected synthetic input]')
    for pattern in patterns:
        if pattern.search(text):
            errors.append(relative + ': possible private material; inspect locally')
if errors:
    raise SystemExit('\n'.join(errors))
print(f'PASS: {len(paths)} tracked source files checked; no matched secrets/private paths or excluded artifacts.')
