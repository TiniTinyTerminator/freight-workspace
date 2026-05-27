Output freight-add-tui.gif

Set Shell "bash"
Set FontSize 13
Set Width 1280
Set Height 720
Set Padding 20
Set Theme "Dracula"
Set PlaybackSpeed 1.0
Set TypingSpeed 55ms

Hide
Type "cp -r /tmp/demo-tui /tmp/demo-tui-run && cd /tmp/demo-tui-run"
Enter
Show

Type "freight add"
Enter
Sleep 3s

Type "zlib"
Sleep 2s

Down
Sleep 500ms
Down
Sleep 500ms
Up
Sleep 400ms

Sleep 1s
Enter
Sleep 1.5s

Ctrl+A
Type "abseil"
Sleep 2.5s

Down
Sleep 500ms
Enter
Sleep 1.5s

Down
Sleep 400ms
Enter
Sleep 1.5s

Escape
Sleep 800ms

Type "cat freight.toml"
Enter
Sleep 2s
