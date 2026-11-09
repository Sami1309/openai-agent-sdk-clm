## Your context is COMPACTED automatically: put every batch on disk the turn it arrives

When your retained context reaches about three quarters of its budget (~24.6K of 32,768),
the harness stops you at the top of a step and a separate model call writes a handoff
summary. Everything except the system prompt and this task text is then replaced by a
single message, "Another language model started to solve this problem and produced a
summary of its thinking process ...". There is no other notice, and the batch delivered on
the turn just before can be inside the summarized span, so an operation you have not acted
on yet can be gone. Queries ask for exact message text and exact integer counts over the
whole log; no summary can hold that. The disk survives every compaction. So on the SAME
turn a `LOG-BATCH` arrives -- a block of 14, 27 or 54 log lines, between about 2,500 and
8,900 characters -- copy it into its own file and release the next operation, in one
command:

```
mkdir -p /tmp/store && cat > /tmp/store/log-0000.log <<'BATCH_EOF'
<the whole block, from its <<<LOG-BATCH 0000#a1b2c3d4 BEGIN ...>>> line through its
<<<LOG-BATCH 0000#a1b2c3d4 END>>> line, copied exactly>
BATCH_EOF
grep -q 'LOG-BATCH 0000.* END>>>' /tmp/store/log-0000.log && grep -cE '^[0-9]{4}-' /tmp/store/log-0000.log && echo 'stored 0000 lines 0-19' && echo READY_FOR_NEXT_OP
```

Four things about it matter:

- **A distinct file per batch** (`log-0000.log`, `log-0001.log`, ...). Reuse one name and
  each batch overwrites the last, and every line but the newest batch is gone.
- **The printed number is the transcription check.** `grep -cE '^[0-9]{4}-'` counts the log
  lines that actually reached the file. The operation arrived under a
  `log batch (lines A-B)` header, so that number must equal B-A+1. Anything less means the
  paste was cut short; redo it.
- **`&&` before the marker.** `grep -q` fails when the END sentinel never made it to disk,
  so a bad paste does not release the next operation and the turn comes back to you.
  Written with `;`, the next batch arrives on top of the one you never stored.
- **Quote the heredoc delimiter** (`<<'BATCH_EOF'`) so each line is written through
  unchanged, and keep the `echo 'stored ...'` line: one short sentence saying where the log
  is, in your newest turn, is what the handoff summary is most likely to carry.

Every batch is delivered before the first `QUERY`, so by query time the whole log must be
on disk. Check that before answering any count:

```
grep -hE '^[0-9]{4}-' /tmp/store/*.log | wc -l
```

This has to equal B+1 of the last `log batch (lines A-B)` header you saw. A count is the
one answer that comes back wrong without ever looking wrong: a batch that never reached
disk is silently missing from it, while a lookup for a line in one of the other batches
still succeeds, so nothing tells you. Short means a batch is still only in your context;
store it, see the total come right, and only then count.

```
n=$(grep -h '\[ERROR\] auth-svc req=' /tmp/store/*.log | wc -l)
printf '<<<ANSWER qid=12>>>\n%s\n<<<ANSWER END>>>\n' "$n"; echo READY_FOR_NEXT_OP
```

```
msg=$(grep -hE '^[0-9]{4}-.* req=ab12cd34 ' /tmp/store/*.log | head -1 | sed 's/^.* req=[^ ]* //')
test -n "$msg" && printf '<<<ANSWER qid=3>>>\n%s\n<<<ANSWER END>>>\n' "$msg" && echo READY_FOR_NEXT_OP
```

Use `grep -h ... | wc -l`, never `grep -c` across several files, which prints one number
per file. Match the level and service the question names, exactly; the trailing ` req=`
keeps the question's own text from counting as a line.

**Also keep your own trace short.** Storing every batch still leaves your own text piling up:
a paste, a verification line and any reasoning you write, once per batch. Keep it to one short
line per turn -- the `grep -c` number is your record, so per-batch notes buy nothing, and one
`grep` at query time covers every file. Short turns matter twice here. They push the next
checkpoint further out, and they leave more of the recent history inside the checkpoint call,
which is given this task text and then as much history as fits with the oldest dropped first:
a batch that has been delivered but not yet stored survives only if the summarizer can still
see it.

**What confirms a compaction** is a conversation that has become one user message beginning
"Another language model started to solve this problem", with the `[context: ~N/M tokens]`
readout back near zero on your next command. Your files are untouched by it, so run
`echo READY_FOR_NEXT_OP` and carry on storing. If the summary you are handed does not name
`/tmp/store`, write that one line back into your next turn so the next checkpoint carries it.

Never emit an empty ANSWER. If `grep` comes back with nothing, that batch is still in your
context rather than on disk, so answer from the conversation and then store it. Never
release an operation before the file verifies, never answer from memory, and never `cat` a
stored file back: that is a second copy of the batch in the context you are keeping small.
