# Get the directory where this PowerShell script is located
$ScriptPath = $PSScriptRoot

# Change the current location to the script's directory
cd $ScriptPath

# --- Log Rotation ---
$LogFile = "sync.log"
$MaxLogSize = 1048576 # 1 MB in bytes

# Check if the log file exists and if its size exceeds the maximum
if (Test-Path $LogFile) {
    $LogSize = (Get-Item $LogFile).Length
    if ($LogSize -gt $MaxLogSize) {
        # Rename the old log file, overwriting any previous backup
        Rename-Item -Path $LogFile -NewName "sync.log.old" -Force
        Write-Host "Log file exceeded 1MB. Rotated to sync.log.old"
    }
}

# --- Script Execution ---
# Add a timestamp to the output log file
$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$LogMessage = "[$Timestamp] Running Python sync script..."
$LogMessage | Out-File -FilePath $LogFile -Append

# Run the python script and append its output (both standard and error) to the log file
# The -u flag ensures output is unbuffered and written immediately
python.exe -u .\sync_script.py >> $LogFile 2>&1
