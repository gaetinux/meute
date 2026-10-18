# meute.cli

CLI tests that touch tmux run through the `sandbox` fixture, which always sets
`MEUTE_TMUX_SOCKET=meute-test-<uuid>` and kills that server at the end.
