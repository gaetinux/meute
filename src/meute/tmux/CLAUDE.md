# meute.tmux

Tests only on a throw-away tmux server (`tmux_server` fixture, socket `meute-test-<uuid>`,
configuration `/dev/null`), always killed at the end. Never call tmux without `-L`, and never
target the `meute` socket.
