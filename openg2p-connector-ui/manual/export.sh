#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
VPY="$(pwd)/.venv/bin/python"

if [[ ! -x "$VPY" ]]; then
  echo "Create venv: python3 -m venv .venv && .venv/bin/pip install pypandoc-binary pillow playwright"
  exit 1
fi

if [[ -f make-reference-docx.py ]]; then
  echo "Building reference.docx..."
  "$VPY" make-reference-docx.py
fi

"$VPY" -c "
import os, pypandoc
os.chdir('$(pwd)')
extra = ['--toc', '--toc-depth=3']
if os.path.exists('reference.docx'):
    extra += ['--reference-doc', 'reference.docx']
pypandoc.convert_file('USER-MANUAL.md', 'docx',
                      outputfile='OpenG2P-Connector-User-Manual.docx',
                      extra_args=extra)
print('Wrote OpenG2P-Connector-User-Manual.docx')
"

if [[ -f postprocess-docx.py ]]; then
  echo "Post-processing for Google Docs..."
  "$VPY" postprocess-docx.py OpenG2P-Connector-User-Manual.docx
fi

ls -lh OpenG2P-Connector-User-Manual.docx
