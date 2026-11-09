## Nothing here removes text from your context: spend the budget on the stream, not on yourself

Every operation arrives as a message in this conversation and stays in your context for the
rest of the run; there is no command, tool or edit that takes it back out. Your own turns —
commands, notes, reasoning — are in the same context and cost from the same 32,768-token
budget, of which about 30,720 is usable. After every command the result ends with
`[context: ~N/M tokens]`, which is the live reading of what the stream plus your own text has
consumed. Since nothing you can run makes the delivered batches smaller, the whole of your
control is in how little you add. So on a `SET-BATCH`, run one command and nothing else:

```
echo READY_FOR_NEXT_OP
```

Three things about it matter:

- **Do not copy batches to disk.** A `cat` heredoc paste duplicates the batch into your
  context as your own text: it costs the full size of what it stores, and removes nothing. The
  batch is already in front of you, so the copy buys no recall you do not already have.
- **Do not write running notes or per-batch confirmations.** A line of prose per batch is a
  second stream running alongside the real one, and it is spent on text you can already see.
- **Keep the marker standalone on batch turns.** Anything else bundled into that command adds
  its own text and its own output to the context for no return; the batch turns need nothing
  done to them at all.

When a `GET <key>` arrives, find the `SET <key> = ` line in the batch that is sitting in your
context and print its value verbatim:

```
printf '<<<ANSWER key=K00084>>>\n%s\n<<<ANSWER END>>>\n' "<the value, copied exactly>"; echo READY_FOR_NEXT_OP
```

Copy the whole value — every word of it, in order, with the original spacing — and stop at the
end of the line. The values are random tokens, so grading compares them character by
character: a dropped word or a tidied-up space is scored the same as no answer at all. Answer
each GET on the turn it arrives; an ANSWER block you have already printed stays counted, so
never spend a turn reprinting one.

What confirms an answer is the ANSWER block coming back in the command output, with the value
between the two sentinels. What tells you where you stand is the `[context: ~N/M tokens]`
readout after every command: it is the only reading you get of how much of the budget the
stream has taken, and it should rise by the size of each batch and by almost nothing else.

**Also keep your own trace short.**

Nothing here reclaims a token, so every line you write is subtracted from the stream you can
still receive. One command per batch turn: no notes, no plans, no acknowledgements, no reasoning
written out into the context. A batch is about 19,600 characters, roughly 5K tokens, and the
usable 30,720 tokens hold about six of them -- so a paragraph of prose per batch costs you a
whole batch of keys before the end of the run.

Read the `[context: ~N/M tokens]` line as a countdown: the gap between N and M, divided by about
5K, is roughly how many more batches you can still take in. The GETs arrive after the batches,
so every batch you survive is more of the stream you are present to answer from, and keys come
in contiguous ranges, so a `GET K00084` is always in the batch whose range covers `K00084` --
you never have to search further than that one block.

Never emit an empty ANSWER block. Never paraphrase, truncate or re-space a value. Every batch
you have been given is still in your context, so the `SET` line for any key is there to find —
keys arrive in contiguous ranges, so go to the batch whose range covers it and copy the value.
