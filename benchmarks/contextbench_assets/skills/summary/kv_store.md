## Your context is replaced by a handoff summary: put every batch on disk before that happens

At three quarters of the budget (about 24.6K of 32,768 tokens) the harness stops you at the
top of a step, before you act, and asks for a CONTEXT CHECKPOINT COMPACTION handoff summary
for another model that will resume the task. Everything except the system prompt and this task
message is then replaced by one message beginning "Another language model started to solve
this problem and produced a summary of its thinking process", and nothing else. The values are
random tokens, far more than any summary can hold, so the batches cannot survive in
prose. Files you write do survive it. So on the SAME turn a `SET-BATCH` arrives, copy the
whole block — all 100 `SET` lines, about 19,600 characters — to its own file and release the
next op, with only the batch id substituted:

```
mkdir -p /tmp/store && cat > /tmp/store/kv-0000.txt <<'EOF'
<paste the block exactly, from its <<<SET-BATCH 0000#... BEGIN line through its <<<SET-BATCH 0000#… END>>> line>
EOF
grep -q 'SET-BATCH 0000.* END>>>' /tmp/store/kv-0000.txt && grep -c '^SET ' /tmp/store/kv-0000.txt && echo READY_FOR_NEXT_OP
```

Four things about it matter:

- **A distinct file name per batch** (`kv-0000.txt`, `kv-0001.txt`, ...). Reuse one name and
  each batch overwrites the last.
- **The quoted `'EOF'` delimiter.** Values may contain `$`, backticks or backslashes; with an
  unquoted delimiter the shell expands them and what lands on disk is no longer the graded
  string.
- **The `&&` chain on the END sentinel.** If the paste was cut short, `grep -q` fails, the
  marker never runs, and the turn comes back with the batch still in hand. Written with `;`
  the next batch arrives on top of one you never stored.
- **Same turn, never later.** The check happens at the top of a step, so a batch delivered on
  the previous turn can be swallowed into summary prose before you act on it; storing it
  immediately is the only safe timing.

A batch plus its paste is roughly 10K tokens, so the 24.6K threshold comes round about every
second batch. That is expected once the batch is on disk: never defer a paste to postpone a
checkpoint.

The checkpoint call carries this task text and as much recent history as fits. Write the
summary as a pointer, not an inventory:

`All SET batches 0000-00NN are stored verbatim in /tmp/store/kv-<id>.txt. Answer every GET
with: grep -h '^SET <key> = ' /tmp/store/*.txt. Remaining work: the GET ops; each is answered
with an ANSWER block. The next op is released by running echo READY_FOR_NEXT_OP.`

If a batch is visible in the history being summarized but its file was never written, copy its
`SET` lines verbatim into the summary as well — that text is the only copy left. When a
`GET <key>` arrives:

```
v=$(grep -h "^SET K00084 = " /tmp/store/*.txt 2>/dev/null | head -1 | sed 's/^SET [^ ]* = //')
[ -n "$v" ] && printf '<<<ANSWER key=K00084>>>\n%s\n<<<ANSWER END>>>\n' "$v" && echo READY_FOR_NEXT_OP
```

What confirms the store is the `grep -c` count coming back as 100. What confirms a compaction is a history that is now one message beginning
"Another language model started to solve this problem", with the `[context: ~N/M tokens]`
readout back near zero. Then run `echo READY_FOR_NEXT_OP` to resume the stream.

**Also keep your own trace short.**

The paste is the expensive half of every batch turn, and your own text decides how much room is
left beside it. One short line per batch turn is enough: the verification count is printed for
you, so you never need an inventory of which batches are stored, and one `grep` covers every
file at query time. Short turns also keep more history inside the checkpoint call, which takes
this task text and then as much recent history as fits, oldest dropped first -- so a batch
delivered but not yet stored is likelier to still be visible to the summarizer.

Never emit an empty ANSWER block: if the guard suppressed it and the batch is still in your
context, read the value there -- keys arrive in contiguous ranges, so it is the batch whose
range covers the key -- answer from it, then store that batch. Never write values into the
summary instead of the file, and never count a batch as stored because you issued the command.
