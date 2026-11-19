# Removes the scheduled tasks. Your data\ folder is kept.
foreach ($n in 'Outreach', 'Inbox') {
    Unregister-ScheduledTask -TaskName $n -TaskPath '\EmailAutopilot\' -Confirm:$false -ErrorAction SilentlyContinue
}
Write-Host 'Scheduled tasks removed. Delete the folder to remove everything else.'
