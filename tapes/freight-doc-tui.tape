Output freight-doc-tui.gif

Set Shell "bash"
Set FontSize 13
Set Width 1280
Set Height 720
Set Padding 20
Set Theme "Dracula"
Set PlaybackSpeed 1.0
Set TypingSpeed 55ms

Hide
Type "cd /home/max/freight/crates/docify/examples/doc-example"
Enter
Show

Type "docify browse libs/"
Enter
Sleep 3s

# Search for "mean" — filters to stats::mean with auto-expanded tree
Type "mean"
Sleep 1.5s

Down
Sleep 300ms
Down
Sleep 300ms
Down
Sleep 300ms
Down
Sleep 300ms
Down
Sleep 300ms
Down
Sleep 400ms

Sleep 1.5s

Tab
Sleep 1.5s

Tab
Sleep 800ms

# Clear "mean" (4 chars), search for "linreg"
Backspace
Backspace
Backspace
Backspace
Sleep 300ms

Type "linreg"
Sleep 1.5s

Down
Sleep 300ms
Down
Sleep 300ms
Down
Sleep 300ms
Down
Sleep 500ms

Sleep 1.5s

# Clear "linreg" (6 chars), search Fortran with "scale"
Backspace
Backspace
Backspace
Backspace
Backspace
Backspace
Sleep 300ms

Type "scale"
Sleep 1.5s

Down
Sleep 300ms
Down
Sleep 500ms

Sleep 1.5s

Escape
Sleep 500ms
