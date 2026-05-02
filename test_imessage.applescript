tell application "Messages"
    set targetService to 1st service whose service type = iMessage
    set targetBuddy to buddy "floriace@icloud.com" of targetService
    send "Test from Phoebus" to targetBuddy
end tell
