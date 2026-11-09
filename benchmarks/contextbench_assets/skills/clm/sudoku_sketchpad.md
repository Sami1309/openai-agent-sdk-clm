## Your method: edit the board IN PLACE with one `python3` heredoc per move

**Your first turn surfaces the board.** Nothing is in your context to edit yet, so
print the whole board with that first move applied and its `VERSION:` line set to the
version that message names -- every version has to be displayed, and this one only
exists if you print it. Print it with a quoted heredoc, whose body is taken literally,
so nothing in the board needs escaping and a stray quote cannot swallow the rest of the
command:

```
cat <<'EOF'
<<<SKETCHPAD BEGIN>>>
VERSION: <the version this message names>
<the 16 rows, that one cell already filled in>
<<<SKETCHPAD END>>>
EOF
```

The cell you fill keeps its own coordinates: a tuple is `(row,col,value)`, so
`Place D in cell r1c1` becomes `(1,1,D)`. Writing the value into the row slot --
`(D,1,D)` where `(1,1,D)` was meant -- is the single most common way this first turn
is lost, and because the board is then wrong from version 1 onward it costs the entire
run, however correctly every later move is applied.

**Every move after that is exactly this command, with three things substituted.**
Your context is mirrored to a file you can edit; changing that file changes what you
are holding. Copy this shape every turn -- do not invent a new way to locate the cell,
and do not write a helper script to call later:

```
python3 - <<'PY' && echo READY_FOR_NEXT_OP
import pathlib, re
f = '/tmp/.live_ctx/LIVE_CTX_MAIN.txt'; t = open(f).read()
i = [m.start() for m in re.finditer(r'(?m)^<<<SKETCHPAD BEGIN>>>$', t)][-1]
h, b = t[:i], t[i:]
b, n = re.subn(r'\(1,3,[^)]*\)', '(1,3,D)', b, count=1)
assert n == 1, 'no such cell'
b = re.sub(r'(?m)^VERSION: .*$', 'VERSION: 2', b, count=1)
e = b.index('<<<SKETCHPAD END>>>') + len('<<<SKETCHPAD END>>>')   # end of the live board
k = b.index('=== board 1 move v2 ')                                # this move's header, as delivered
b = b[:e] + '\n' + b[k:]                                          # drop old moves + your own commands
open(f, 'w').write(h + b)
print(re.search(r'(?m)^VERSION: .*$', b).group(0),
      [len(re.findall(r'\(\d+,\d+,', r)) for r in b.split('\n') if r.startswith('(')][:16])
PY
```

That example puts `D` into row 1 column 3 and makes the board version 2. You substitute
three things and nothing else -- the row and column in the pattern, the finished tuple,
and the new version number -- all three read straight off the move you were just given.
The pattern has no `^`: a cell sits in the middle of its row, so anchoring it to a line
start matches nothing.

**The last line prints what actually landed, and it is the whole point.** It comes back
as the new `VERSION:` line followed by sixteen `16`s:

```
VERSION: 2 [16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16]
```

That one line answers the only two questions you can have after an edit -- did the
version move, and is the board still whole -- so you never have to wonder whether the
command worked. **Read it, then go straight to the next move.** Do not send the same
edit again "to be sure", and never send `echo READY_FOR_NEXT_OP` on its own: the edit
command already carries the marker, so a bare one releases a move that no edit of yours
will ever apply, and every version from there on is wrong. A number below 16 names the
row that lost a cell while you were typing the board -- fix that one row inside the same
kind of command, `b = re.sub(r'(?m)^\(3,1,.*$', '<row 3, all sixteen tuples>', b, count=1)`.

**Why the board is found this way, and why the whole run turns on it.** The board is
in your context more than once, and only one of the copies is graded. Your first turn
printed it, so a copy sits inside the text of that command of yours; and from your
second move on, every command you send quotes `<<<SKETCHPAD BEGIN>>>` as a string, so
those commands are copies too. Pick the wrong one and the edits pile up somewhere
harmless while the graded board keeps its version bumped and its cells empty -- every
edit reporting success the whole way, and nothing looking wrong from the inside.

Two rules find the right one. `(?m)^...$` matches only where the sentinel is alone on
its own line, which is true of the real board and never of a command (a command reaches
your context as one escaped line, so its `\n` are two characters and not line breaks).
And `[-1]` takes the last such match, which is the live board. Slicing there and
searching only `b` keeps both substitutions below inside it.

**The `e`/`k` lines keep your own turns from filling the window.** Every command you send
and every note the harness returns is mirrored too, so over a long ladder that residue is the
bulk of your context. After the edit lands, everything between the live board's END line and
this move's header -- all earlier move messages and all your earlier commands -- is cut, and
the move you are answering is kept. Substitute the header exactly as it was delivered.

**Why `1` and `count=1`.** Inside the live board a cell tuple and the `VERSION:` line
each occur exactly once, so these counts are belt-and-braces: they stop a mistyped
anchor from rewriting more than the one thing you meant.

`re.sub` on `^VERSION: .*$` replaces that line whatever number is on it, so you never
have to know or guess the board's current version. Do not match the old number instead:
if one edit ever fails to land, the board stays a version behind and a pattern naming
the old number misses every turn after that, for the rest of the run.

**The `assert` and the `&&` are what keep you honest.** If the cell text is not in the
file the assert stops the command non-zero, the `&&` withholds `READY_FOR_NEXT_OP`, and
the next move is NOT released -- so the turn comes back to you and the anchor can be
fixed. Written with `;` instead, the next move would arrive on top of the one you never
applied, and that version could never be displayed again.

Confirm each move landed by the note the harness sends back:

```
[LIVE_CTX_MAIN.txt: edit applied - context ~11431->11433 tokens, 7 turns]
```

No note means the board did not move, whatever the command printed. If a turn does not
land -- an assert, a shell error, no note, or a turn that made no tool call at all --
the board is still at the version it was and the move you were given has NOT been
applied. Never skip it and never jump the version forward to catch up: apply the missed
move first, as its own command, and only then the move that just arrived.

Do NOT re-print the whole board and do NOT let old versions pile up. On a NEW BOARD,
print the fresh one and delete the previous one in the same style: read the file, cut
from `<<<SKETCHPAD BEGIN>>>` through the first `<<<SKETCHPAD END>>>`, write it back.

Never print, `cat` or `grep` the mirror file. The board is already in your context, so
a dump only puts a second copy of it there, and a second copy is exactly what the
first-occurrence rule above cannot protect you from.

Two things the harness will say that are NOT problems, and that you must not act on. A
per-turn note that the context GREW by a token or two: that is the new turn being
recorded, not a duplicated board, and in-place edits cannot shrink it. And the archived
copies under `/tmp/.live_ctx/archived_ctx/`: never restore one, since that rolls the
board back to an older version and every later edit then lands wrong.

Do not compact this context: the run needs a small fraction of your budget, and a
compaction can take the board with it.
