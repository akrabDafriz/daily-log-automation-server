# Get the directory where this PowerShell script is located
$ScriptPath = $PSScriptRoot

# Change the current location to the script's directory
cd $ScriptPath

# Execute the Python script
# Add a timestamp to the output log file
$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$LogMessage = "[$Timestamp] Running Python sync script..."
$LogMessage | Out-File -FilePath "sync.log" -Append

# Run the python script and append its output (both standard and error) to the log file
python.exe -u .\sync_script.py >> sync.log 2>&1