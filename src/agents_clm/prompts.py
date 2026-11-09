"""The system prompt section that teaches an agent about its context file."""

CONTEXT_PROMPT = """

## Managing your context

Your context budget is {limit} tokens, and tool results report your current size.

Your conversation is mirrored to `{path}`. **That file is your context.** What you leave in it \
is what you will see on your next turn. If you don't edit it, new turns are appended. Use your \
shell to replace stale regions (large outputs, dead ends, superseded notes) with concise, \
specific notes, or to move material to other files in your workspace.

Turns look like `[[CTX_TURN 7 role=tool]]`, numbered from the top of the file. Your system prompt \
and original task are not in the file and cannot be changed. Keep the header of any turn you \
keep: a turn with no text is dropped. You may add turns, including with new roles such as \
`role=notes`.

Locate text with code rather than retyping it, and don't print the file, because its text is \
already in your context:

```bash
python3 - <<'PY'
import re
p = "{path}"
s = open(p).read()
s = re.sub(r"(\\[\\[CTX_TURN 7 [^\\]]*\\]\\]).*?(?=\\n\\[\\[CTX_TURN|\\Z)", r"\\1\\n[note: parser.py:142 drops quoted commas]", s, flags=re.S)
open(p, "w").write(s)
PY
```

Your own earlier commands are in the file too, so a broad pattern can match text inside them \
and delete far more than you meant. Match a turn by its header, or a block by a line that is \
unique to it, and confirm that the size in the edit note fell by about what you expected.

Edits take effect on your next turn. An edit makes everything after it get reprocessed, so \
combine edits into one command and prefer editing recent turns over old ones.
"""
