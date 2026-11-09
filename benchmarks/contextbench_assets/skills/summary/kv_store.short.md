## Your context is COMPACTED (summarized) automatically

When your context grows large, the harness replaces earlier messages with a
summary you write. That summary MUST preserve every `SET <key> = <value>` pair
**verbatim** - the values are random tokens, so anything you abbreviate or omit
is lost permanently and the corresponding GET will be graded wrong. When a `GET
<key>` arrives, emit the ANSWER block with the stored value.

## You MAY copy values to disk, but copying does NOT free your context

Every operation is delivered as a message and therefore lands IN YOUR CONTEXT and
stays there — you cannot keep it out (there is no command to fetch it, so there is
nothing to redirect). You may duplicate content to a file for later search by
pasting lines from your context into a `cat` heredoc, e.g.:

```
mkdir -p /tmp/store
cat >> /tmp/store/kv.txt <<'EOF'
<paste the SET lines you want to keep, copied from your context>
EOF
```

and read it back later with `grep 'SET <key> =' /tmp/store/kv.txt`. IMPORTANT:
this only DUPLICATES text onto disk — it does not remove anything from your
context. Your context shrinks only through the mechanism described above (if any);
with no way to remove old content, a long stream will eventually exceed your budget.
