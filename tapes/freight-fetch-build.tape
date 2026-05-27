Output freight-fetch-build.gif

Set Shell "bash"
Set FontSize 13
Set Width 960
Set Height 576
Set Padding 20
Set Theme "Dracula"
Set PlaybackSpeed 1.0
Set TypingSpeed 55ms

Hide
Type "cp -r /tmp/demo-fetch /tmp/demo-fetch-run && cd /tmp/demo-fetch-run && rm -rf .deps target freight.lock"
Enter
Show

Type "cat freight.toml"
Enter
Sleep 2s

Type "freight fetch"
Enter
Sleep 5s

Type "freight build"
Enter
Sleep 14s

Type "./target/dev/demo"
Enter
Sleep 1.5s
