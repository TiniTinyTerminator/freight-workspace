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
Sleep 7s

# Search for a package
Type "zlib"
Sleep 2.5s

# Navigate the list
Down
Sleep 500ms
Down
Sleep 500ms
Up
Sleep 400ms
Sleep 1s

# Tab to Versions pane
Tab
Sleep 800ms

Down
Sleep 400ms
Down
Sleep 400ms
Sleep 600ms

# Toggle to Dependencies tab with 't' (only fires when Versions pane is focused)
Type "t"
Sleep 1.2s

# Back to Versions tab
Type "t"
Sleep 800ms

Down
Sleep 400ms
Sleep 1s

# Tab to README/Details pane
Tab
Sleep 600ms

Down
Sleep 300ms
Down
Sleep 300ms
Down
Sleep 300ms

# Tab back to Packages
Tab
Sleep 500ms

# Add the selected package
Enter
Sleep 1.5s

# Search for another package
Backspace
Backspace
Backspace
Backspace
Sleep 400ms

Type "abseil"
Sleep 2.5s

Down
Sleep 500ms
Enter
Sleep 1.5s

Escape
Sleep 800ms

Type "cat freight.toml"
Enter
Sleep 2s
