@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "DriveUSB="
set "VolumeName=SD-Card"
:GetDriveLetter
for /F "tokens=2 delims==" %%I in ('%SystemRoot%\System32\wbem\wmic.exe LOGICALDISK where VolumeName^="%VolumeName%" GET DeviceID /VALUE 2^>nul') do set "DriveUSB=%%I"
if not defined DriveUSB (
    echo Device with name %VolumeName% not found.
    echo/
    %SystemRoot%\System32\choice.exe /C YN /N /M "Retry (Y/N):"
    if errorlevel 2 goto :EOF
    goto GetDriveLetter
)
echo Drive letter of %VolumeName% is: %DriveUSB%
rem More commands using environment variable DriveUSB.
echo/
pause
endlocal
