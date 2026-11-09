## Your method: print the full board each move (no context management)

You have no special context tool. Each move, SURFACE the current board by echoing
the COMPLETE `<<<SKETCHPAD BEGIN>>> … <<<SKETCHPAD END>>>` block (bumped `VERSION:`
line, every tuple, exact format) with the `bash` tool, e.g.:

    cat <<'EOF'
    <<<SKETCHPAD BEGIN>>>
    VERSION: <n>
    ...all tuples...
    <<<SKETCHPAD END>>>
    EOF

Do this on EVERY move (and right after a NEW BOARD). Just keep re-printing the
whole board and let your context grow — you do not compress or delete anything.
