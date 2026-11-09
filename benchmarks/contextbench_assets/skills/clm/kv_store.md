## Keep your context small: OFFLOAD each SET-BATCH with one `python3` heredoc

The values are far too many to keep in your context, and you cannot predict which
keys will be queried. Your context is mirrored to a file you can edit; changing that
file changes what you are holding. So on the SAME turn you read a `SET-BATCH`, move
the whole block out of your context and onto disk with this one command, with only
the batch id substituted:

```
python3 - <<'PY' && echo READY_FOR_NEXT_OP
import pathlib
p = pathlib.Path('/tmp/.live_ctx/LIVE_CTX_MAIN.txt'); t = p.read_text()
a = '<<<SET-BATCH 0001#abc123 BEGIN'
prev = '[batch 0000 offloaded]'          # the placeholder you wrote last turn; prev = None on the first batch
i = t.index(a); j = t.index('END>>>', i) + len('END>>>')
d = pathlib.Path('/tmp/ctx_offload'); d.mkdir(exist_ok=True)
(d / 'kv-0001.txt').write_text(t[i:j])
head = t[:t.index(prev) + len(prev)] if (prev and prev in t[:i]) else t[:i]
p.write_text(head + '\n[batch 0001 offloaded]' + t[j:])
PY
```

Five things about it matter:

- **`prev` is last turn's placeholder.** Everything between it and this batch is your own
  previous command, the harness note and the marker turn -- text that is mirrored too and
  would otherwise pile up one turn per batch until the window is full. The `head` line cuts
  it away in the same edit, so your context after every batch is the task text plus one
  placeholder line per batch. On the first batch set `prev = None`.

- **`t.index(a)` finds the FIRST occurrence,** which is what you want: the batch
  arrives in the conversation before any command of yours mentions it, so the earliest
  copy is always the real one, and your own command text is always later.
- **`j` searches from `i`,** so `END>>>` pairs with this batch's START line and not
  some other batch's.
- **A distinct file name per batch.** Reuse one name and each batch overwrites the
  last, and every value but the newest is gone.
- **`&&` before the marker.** `t.index` raises if the anchor is not there, so a failed
  offload does not release the next operation and the turn comes back to you. Written
  with `;` the next batch arrives on top of the one you never offloaded.

Everything removed lands in `/tmp/ctx_offload/`, so when a `GET <key>` arrives you
recover the value with `grep -h 'SET <key> =' /tmp/ctx_offload/*` and then print the
`<<<ANSWER ...>>>` block. Do this for EVERY batch: the context never grows and every
value stays recoverable.

Anchor only on text you have actually seen in this conversation -- the batch's own
sentinel line. Do NOT anchor on a `[[CTX_TURN i role=...]]` header: the mirror numbers
its turns internally and you never see that numbering, so the number you guess is
usually not the one the batch is under, and cutting from a turn header takes everything
between it and your end anchor with it.

Never emit an empty ANSWER. If `grep` comes back with nothing, that batch is still in
your context rather than on disk (an offload that raised leaves the data where it was),
so read the value out of the conversation and answer from there, then offload the batch
again.

The edit is silent when it works, which keeps that turn free. What confirms it is the
harness note that comes back with it:

```
[LIVE_CTX_MAIN.txt: edit applied - context ~26731->3335 tokens, 5 turns]
```

No note, or a token count that did not drop, means the batch is still in your context
whatever the command printed -- fix the anchor and run it again. Never count a batch as
offloaded just because you issued the command for it.

Your own trace never needs a separate cleanup: the `prev` cut above removes it every turn. Keep
any note you do write to one short line, and it will be gone next turn with the rest.

Do not compact this context any other way, and never `cat` or `grep` the mirror file:
a dump puts a second copy of a block into your context, and from then on an edit can
land on the stale copy while the live one silently stops moving.
