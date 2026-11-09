## You MAY copy log lines to disk, but copying does NOT free your context

Every operation is delivered as a message and therefore lands IN YOUR CONTEXT and
stays there — you cannot keep it out (there is no command to fetch it, so there is
nothing to redirect). You may duplicate content to a file for later search by
pasting lines from your context into a `cat` heredoc, e.g.:

```
mkdir -p /tmp/store
cat >> /tmp/store/log.txt <<'EOF'
<paste the log lines you want to keep, copied from your context>
EOF
```

and search it later with `grep 'req=<id>' /tmp/store/log.txt` (lookup) or
`grep -c '\[ERROR\] auth-svc' /tmp/store/log.txt` (count). IMPORTANT: this only
DUPLICATES text onto disk — it does not remove anything from your context. Your
context shrinks only through the mechanism described above (if any); with no way
to remove old content, a long log will eventually exceed your budget.
