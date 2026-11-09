## Your method: nothing shrinks your context -- spend the budget on the stream, not on yourself

You have no context mechanism. Every operation is delivered as a message, lands in your
context and stays there; there is no command that removes it and nothing to redirect,
because you never fetch anything. Your budget is 32,768 tokens, usable about 30,720, and
the `[context: ~N/M tokens]` line after every command is your only gauge. When the retained
context exceeds the budget you get one final turn and the run ends, with no rollback and no
retry; everything you answered before that still counts. The whole log is delivered before
the first `QUERY`, so how far into the stream you survive decides how many questions you
ever get to see. That makes your own text the only thing you can spend less of. On a
`LOG-BATCH`, release the next operation and do nothing else -- no note, no reasoning
paragraph, no copy:

```
echo READY_FOR_NEXT_OP
```

Three things about it matter:

- **Copying a batch to a file cannot help you.** The batch is already in your context, and
  the heredoc you would type to save it is your own turn, so the copy puts a second full
  version of the batch into the context and roughly halves how much of the log you reach.
  The disk is not the constraint here; the context is.
- **One line per turn.** A sentence of commentary per batch is a batch of log lines you do
  not get to hold by the end of the stream.
- **Answer every query the moment it arrives.** The log is in your context, so the answer
  is available now and may not be later.

A lookup asks for the message of the line carrying a given `req=` id. Find that line in the
batch where it was delivered and print everything after the id, the trailing `#` tag
included:

```
printf '<<<ANSWER qid=3>>>\n%s\n<<<ANSWER END>>>\n' 'timeout retry connection refused #ff00aa11'; echo READY_FOR_NEXT_OP
```

A count is over the whole log, which means every batch from the first to the last, and the
arithmetic is where it goes wrong, not the reading. Work batch by batch in
`log batch (lines A-B)` order, count the lines matching the level and service the question
names in each batch, and let the shell add them up in one command, one number per batch and
zeros included:

```
n=$(printf '%s\n' 7 3 0 5 9 2 | awk '{s+=$1} END {print s}')
printf '<<<ANSWER qid=12>>>\n%s\n<<<ANSWER END>>>\n' "$n"; echo READY_FOR_NEXT_OP
```

Check completeness against the headers before you trust the sum: the batches you have run
`lines 0-A`, `lines A+1-C`, ... with no gap, the last header's B+1 is the length of the
whole log, and you must have contributed exactly one number per header. A skipped header is
a silently low count that looks like every other count.

What confirms anything here is only the `[context: ~N/M tokens]` readout and the ANSWER
block you printed coming back in the transcript. There is no harness note to wait for.

**Also keep your own trace short.** Nothing here reclaims a token, so every line you write is
subtracted from the stream you can still receive. One command per batch turn: no notes, no
plans, no acknowledgements, no reasoning written out into the context. A 54-line batch is about
8,900 characters, roughly 2.2K tokens, so a paragraph of commentary per batch costs you several
batches of log across the run -- and the whole log is delivered before the first `QUERY`, so the
batches you lose at the end are the ones a count needs most.

Read the `[context: ~N/M tokens]` line as a countdown: the gap between N and M, divided by what
one batch costs you, is how many more batches you can still take in. When it is nearly closed,
stop writing anything but answers.

Never paste log lines into a file, never write summaries or per-batch notes, never re-print
a batch, and never emit an empty ANSWER. When the readout says you are close to the budget,
keep answering: a block emitted on the final turn is scored exactly like the first one.
