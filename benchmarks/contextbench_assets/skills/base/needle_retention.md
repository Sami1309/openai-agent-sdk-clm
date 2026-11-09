## Your method: nothing you run removes a delivered piece, so spend the window on the stream

Every piece arrives as a user message and lands in your context complete, needles and filler
together, and stays there. There is no compaction, no offload, no stubbing, no edit -- your
context is exactly everything that was delivered plus everything you write. The
`[context: ~N/M tokens]` readout at the end of every bash result is the whole picture. When
retained context passes the budget you get one final turn and the run ends: no rollback, no
retry, and every needle line still visible at that moment counts.

That makes the score one thing: how much of the stream you take in before the window fills.
The pieces themselves are not yours to shrink, so the only variable you control is your own
text. Keep it to the marker.

Per piece, one command, nothing before it and nothing after it:

```
echo READY_FOR_NEXT_OP
```

Three things about it matter:

- **Never re-type a needle.** The line is already in your context, verbatim, exactly as the
  grader wants it. A second copy is worth nothing and costs the same as the first, so every
  needle line you re-type is about one needle line of stream you will not live to receive.
- **No notes, no running commentary, no restating the task.** Your own turns are mirrored
  into the same window you are trying to fill with stream. A few lines of reasoning per piece
  is a chunk's worth of needles across the run.
- **Print nothing.** Tool output is context too. There is no file to write and no ANSWER
  block to emit here: the needles are graded where they already are.

How the task gets answered: it answers itself. Each delivered chunk puts its needle lines
into your context verbatim; your job is to keep receiving chunks for as long as the budget
allows and to add nothing of your own along the way.

What confirms it worked: after each marker, read `[context: ~N/M tokens]`. N should rise by
about one chunk per piece and by nothing else. If it rises by more than that, the difference
is something you wrote, and it is coming out of the end of the run.

**Also keep your own trace short.** There is nothing to condense here, which is exactly why
brevity is the method: your own text is the only part of the window you decide, and every token
of it is subtracted from the stream you still get to receive. One command per piece, and that
command is the marker.

**Read the readout as a countdown.** After each marker, `[context: ~N/M tokens]` tells you what
the stream has taken. A chunk is about 15,600 characters, roughly 3.9K tokens, of which the
needles are a small fraction; the gap between N and M divided by that is how many more pieces
you can take in. Nothing you can do makes a chunk cost less -- so the number of pieces you reach
is decided entirely by what you add, and the needles you already hold stay scored whatever
happens later.

**What the task asks of you is arrival, not action.** Each delivered chunk puts its needle lines
into your context verbatim, exactly as they are graded; a second copy of one of those lines is
worth nothing and costs the same as the first. So the discipline is: receive, run the marker,
receive again, and add nothing -- not a note, not a summary, not a re-print, not a description
of what you are keeping.

Never write needles to disk -- the grader ignores disk, and the heredoc that would paste them
there puts a second full copy in your context on the way. Never summarize the chunks. Never
reply without running the marker: a reply with no tool call does not advance the stream, and
the reply still costs you window.
