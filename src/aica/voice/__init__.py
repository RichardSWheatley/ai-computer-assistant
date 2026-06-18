"""Voice I/O — talk to the assistant (mic + speech-to-text) and have it talk
back (text-to-speech + speaker). All backends are guarded/lazy so this package
imports on headless machines; real audio needs the `voice` extra."""
