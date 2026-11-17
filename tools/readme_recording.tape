# The terminal half of the README's recording (#46). Run from the repository root:
#
#     vhs tools/readme_recording.tape
#     python tools/readme_recording.py
#
# Everything typed below runs for real, in a fresh virtual environment in a temporary
# directory, against qedro as published on PyPI: the install, the demo and the three
# records. The second command appends the first page of each PDF it wrote, rendered
# from the same events, and writes docs/images/demo.gif. Rerun both whenever the
# output changes, as tools/readme_image.py is for the still images.

Output build/readme-recording/terminal.gif

Require python3

Set Shell "bash"
Set Theme "Github"
Set FontSize 15
Set Width 1300
Set Height 520
Set Padding 24
Set TypingSpeed 35ms

# Set up out of sight: a temporary directory and an empty virtual environment.
Hide
Type `export PS1='$ ' && cd "$(mktemp -d)" && python3 -m venv .venv && export VIRTUAL_ENV_DISABLE_PROMPT=1 && source .venv/bin/activate && clear`
Enter
Sleep 3s
Show

Type "pip install --quiet --disable-pip-version-check 'qedro[pdf]'"
Sleep 400ms
Enter
Wait+Line@120s /^\$\s*$/
Sleep 800ms

Type "qedro demo acme"
Sleep 400ms
Enter
Sleep 5s

Hide
Type "clear"
Enter
Show

Type "qedro ropa acme/lineage --config acme/qedro.yaml --out mapped.pdf"
Sleep 400ms
Enter
Sleep 3s

Type "qedro ropa acme/lineage-declared --config acme/qedro.yaml --out record.pdf"
Sleep 400ms
Enter
Sleep 3s

Type "qedro erasure acme/lineage-declared --config acme/qedro.yaml --dataset crm_raw.contacts --out erasure.pdf"
Sleep 400ms
Enter
Sleep 4s
