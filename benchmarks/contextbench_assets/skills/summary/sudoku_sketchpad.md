## Your context is compacted into a summary: the current board has to be inside it, verbatim

When your retained context reaches about three quarters of the budget (roughly 24.6K of
32,768 tokens), the harness stops you at the top of a step and has a separate model write a
handoff summary of the work so far. Everything except the system prompt and this task
message is then replaced by one user message: "Another language model started to solve this
problem and produced a summary of its thinking process ...". You carry on from that summary
and nothing else. Your boards, your commands and the moves you were given are gone from the
conversation at that moment -- what is written into the summary is all you keep.

**Every move, print the whole board in one command.** The move you are given names one cell
and the new version id. Copy the sixteen rows of your current board, change that one cell,
put the named id on the `VERSION:` line, and print the block:

```
cat <<'EOF' && echo READY_FOR_NEXT_OP
<<<SKETCHPAD BEGIN>>>
VERSION: <the id this message names>
<all sixteen rows, with that one cell changed>
<<<SKETCHPAD END>>>
EOF
```

The heredoc is quoted, so its body is taken literally: parentheses, dots and the `<<<`
sentinels need no escaping and a stray quote cannot swallow the rest of the command. Type all
sixteen rows out in full -- `...` in place of rows is a wrong board -- flush left, no leading
spaces, one row per line, the same single space between tuples as the board you were given.
Nothing here can check the board for you, so read your own printed output before moving on.

A tuple is `(row,col,value)`. `Place D in cell r1c1` is `(1,1,D)`: rows count from the top,
columns from the left, and the value goes last. Writing `(D,1,D)` where `(1,1,D)` was meant
is the single most common way a run is lost, and the board is wrong from that version on
however correctly every later move is applied.

Three things about this shape matter:

- **The marker rides in the same command,** so the board and the release never come apart: there
  is no turn in which a move was taken but its version went undisplayed.
- **Copy the rows out of your own last print,** never retype them from memory and never go back
  to the board in the task text: each print is the previous one with a single cell changed, and
  a row rebuilt by hand loses moves that were already displayed correctly.
- **One command per turn and no prose beside it.** The compaction fires on the size of the
  retained context, so every line you write brings it forward and buys nothing.

**Write the summary so it survives.** The compaction call is given this task text and as
much of your recent history as fits, oldest dropped first. Any summary written for this task
MUST begin with the most recent `<<<SKETCHPAD BEGIN>>> ... <<<SKETCHPAD END>>>` block copied
character for character -- the `VERSION:` line as it stands and all sixteen rows -- and must
then name, in one line, any move that has been delivered and not yet applied. Nothing else
needs to survive: old boards, old move text and reasoning can all be dropped. A board that is
paraphrased, abbreviated or described instead of copied is a board you no longer have.

Keep every turn to that one command and no prose. The shorter your turns, the more certain it
is that your newest board is inside the window the summarizer reads, and the later the
compaction fires at all.

Apply and print each move on the turn it arrives, never on the next one. Compaction happens
before you act, so a move you are sitting on can be swallowed into summary prose and that
version could then never be displayed.

**A NEW BOARD message** carries a fresh board and its version id: copy that board tuple for
tuple into your next print with the id it names, carry nothing over from the old board, and
never keep both in view.

**If a turn does not land** -- a shell error, or a reply with no tool call -- the move was not
applied and the board is still where it was. Apply the missed move as its own `cat` command,
then the move that just arrived as a second `cat` in the same turn, with the marker on the last
one; both versions are then displayed. Never jump the version forward to catch up: the version
id always comes from the message you are applying, never from your own count.

**After a compaction** the summary is your board. Read the block out of it, apply the next
move on top of it, and print as before. The version id always comes from the message you are
applying, never from your own count -- so even across a compaction the numbering stays right.
Do not treat the summary message as a signal to stop or to give a final answer; run the
marker and keep going.

Your print comes straight back to you as the command's output, so read it: it must start
with `<<<SKETCHPAD BEGIN>>>`, carry the version id the message named, then sixteen rows of
sixteen tuples, then `<<<SKETCHPAD END>>>`. The `[context: ~N/M tokens]` readout after each
command tells you how close the next compaction is.

**Your first turn.** The starting board is printed in this task text; your first print is that
board with the first move applied and the `VERSION:` line set to the id that message names. From
then on, every print is a copy of your OWN last printed block with one cell changed -- take the
rows from your last print, never from the task text again, or every move before it disappears
from the board while the version keeps climbing.

**A worked move.** `Place 7 in cell r4c9`, new version 12: in your last printed block the ninth
tuple of the row-4 line, `(4,9,.)`, becomes `(4,9,7)`; the `VERSION:` line becomes `VERSION: 12`;
every other tuple is character for character what it was. Then the whole block is printed again.
Before you send it, count the tuples in the row you touched -- sixteen, still separated by single
spaces -- because a row that lost a tuple while you were typing is a wrong board from that
version onward, and nothing here will tell you.

**If the summary you are handed has no board in it,** do not invent one and do not start again
from the task text: the last board you printed is gone from the conversation, and a guessed
board is wrong in every cell you cannot recall. Print, on that turn, the most recent board you
can still read anywhere in your context -- including out of the summary's own prose if it quotes
tuples -- with the version it carries, then apply the next move on top of it. A board that is
one version behind and correct beats a board that is current and wrong: the versions you already
displayed are already counted, and every version you display correctly from here is counted too.

**Also keep your own trace short.** The compaction fires on the size of the retained context, so
everything you write brings the next one forward, and everything you write also competes with
your board for room in the summary that survives it. An ordinary move turn is the `cat` command
and nothing else: no reasoning in the context, no "applying move 14" notes, no plans, no
acknowledgement of the compaction beyond the marker. The board block is the only text in this
run worth spending the window on, and the summarizer is given this task text plus as much recent
history as fits, oldest dropped first -- so the shorter your turns, the more certain it is that
your newest board is inside the window it reads.

Never write the board to a file: grading reads only your context. Never re-print an older
version. Never send `echo READY_FOR_NEXT_OP` on its own -- that releases a move for a version
you never displayed, and every version after it is one behind.
