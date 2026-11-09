## Your context is replaced by ONE summary: make that summary the needle lines and nothing else

When your retained context reaches about three quarters of the budget (roughly 24.6K of
32,768), the harness stops you at the top of the step and asks a separate call to write a
CONTEXT CHECKPOINT COMPACTION handoff summary for another model that will resume the task --
current progress, constraints, what remains, and "any critical data, examples, or references
needed to continue". Everything except the system prompt and this task message is then
replaced by one user message: "Another language model started to solve this problem and
produced a summary of its thinking process... Here is the summary produced by the other
language model: <summary>". The chunk delivered on the turn just before can be inside the
collapsed span, so a piece you have not acted on yet can disappear into that prose.

Grading reads the needle lines out of your FINAL context. After a compaction the only place
a needle line can be is inside that summary. So the summary is not a description of your
progress: it IS the needle lines, one per line, and nothing else. They are the critical data
needed to continue, and there is nothing else to report.

Per piece, one command and nothing else:

```
echo READY_FOR_NEXT_OP
```

When the checkpoint request comes, your whole reply is the lines themselves:

```
[n00001i00#a1b2c3d4] ...
[n00001i01#7f0c22de] ...
... every needle line you hold, one per line, copied character for character ...
```

Four things about it matter:

- **Every needle from every chunk, including the ones sitting in the previous summary.**
  A compaction replaces the earlier summary message too. Each checkpoint is a full re-copy
  of everything you have: read the old summary's lines out and write them again, then the
  lines from the chunks delivered since. Anything you do not copy forward is gone for good,
  silently -- the run continues at a comfortable size with half of what it was scored on
  thrown away.
- **Verbatim, the whole line.** The id, the `#hash`, and the words after it. A trimmed tail,
  a re-wrapped line, an ellipsis for "the rest of chunk 4", or an accurate sentence saying
  the needles were preserved all score zero. Grading matches the line, not the claim.
- **No prose, no headings, no filler.** Never copy a `[fNNNNNxNNN#...]` line or a
  `<<<FILLER-BLOCK ... >>>` sentinel; every character you add competes with a needle line
  for the same window.
- **Keep your own turns to the marker.** The compaction call is given the system prompt,
  this task text, then as much recent history as fits, dropping the oldest first. Notes and
  reasoning you write push your earliest chunks out of that call, and a needle the
  summarizer never sees cannot be copied.

What confirms it worked: the next user message opens with "Another language model started to
solve this problem" and your needle lines are inside it, one per line; the `[context: ~N/M
tokens]` readout on your next command drops sharply. Count the lines in that message against
the number of chunks you have received. If any are missing or abbreviated, copy what is
there forward at the next checkpoint and do not abbreviate again.

**Also keep your own trace short.** Between checkpoints your own text competes with the stream
for the same window, and at a checkpoint it competes with your needles for the same summary
call. So the marker is the whole of an ordinary turn: no reasoning written out, no per-chunk
notes, no counting out loud, no plans for the next chunk. The compaction call is given the
system prompt, this task text, and then as much recent history as fits with the oldest dropped
first -- every line you write pushes an earlier chunk out of that call, and a needle the
summarizer never sees cannot be copied into the summary.

**A worked checkpoint.** Say chunks 1 to 12 have been delivered. Your reply to the checkpoint
request is those needle lines and nothing else -- `[n00001i00#a1b2c3d4] ...` through
`[n00012i07#5d3e9a10] ...`, one per line, each copied character for character from where it
sits in your context, including the ones you copied forward at the previous checkpoint. No
heading, no "the needles from chunks 1-12 are:", no trailing note.

Never write the needles to disk instead (the grader ignores disk). Never print them back in
your own output when no summary has been asked for: that copy is replaced by the next
compaction anyway and only brings it forward. Never reply without a tool call on a piece
turn -- it does not advance the stream.
