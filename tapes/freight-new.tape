Output freight-new.gif

Set Shell "bash"
Set FontSize 13
Set Width 960
Set Height 540
Set Padding 20
Set Theme "Dracula"
Set PlaybackSpeed 1.0
Set TypingSpeed 55ms

Hide
Type "cd /tmp && rm -rf demo-new"
Enter
Show

Type "freight new demo-new"
Enter
Sleep 2s

Type "cd demo-new"
Enter
Sleep 500ms

Type "cat freight.toml"
Enter
Sleep 2s

Type "cat src/main.cpp"
Enter
Sleep 2s

Type "freight build"
Enter
Sleep 8s

Type "./target/dev/demo-new"
Enter
Sleep 1.5s
