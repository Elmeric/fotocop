; Fotocop.nsi
;
; This script will install Fotocop into a directory that the user selects.
; It optionnally creates shortcuts in the start menu.

;--------------------------------
!include LogicLib.nsh
!include Integration.nsh

LoadLanguageFile "${NSISDIR}\Contrib\Language files\English.nlf"

; The Application name
!define NAME "Fotocop"

;The root registry to write to
!define REG_ROOT "HKLM"

;The registry path to write to
!define REG_APP_PATH "SOFTWARE\${NAME}"
!define REG_UNINSTALL_PATH "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\${NAME}"

; Set the name of the uninstall log
!define UninstLog "uninstall.log"
Var UninstLog

; Message displyed when the uninstall log file missing.
LangString UninstLogMissing ${LANG_ENGLISH} "${UninstLog} not found!$\r$\nUninstallation cannot proceed!"

; The name of the installer
Name "${NAME}"

; The file to write the installer
OutFile "${NAME} Installer.exe"

; No application privileges are requested
RequestExecutionLevel user

; Build Unicode installer
Unicode True

; The default installation directory
InstallDir "$PROGRAMFILES64\${NAME}"

; Registry key to check for directory (so if you install again, it will 
; overwrite the old one automatically)
InstallDirRegKey "${REG_ROOT}" "${REG_APP_PATH}" "Install_Location"

; The Fotocop distribution location
!define FOTOCOP_DIST "F:\Users\Documents\Python\fotocop\dist\fotocop"

; Create the uninstall log file
;!system "dir /b F:\Users\Documents\Python\fotocop\dist\fotocop > F:\Users\Documents\Python\fotocop\dist\fotocop\uninstall.log"
!system 'dir /b "${FOTOCOP_DIST}" > "${FOTOCOP_DIST}\uninstall.log"'

;--------------------------------

; Pages

Page components
Page directory
Page instfiles

UninstPage uninstConfirm
UninstPage instfiles


;--------------------------------

; The stuff to install
Section "Fotocop (required)"

  ; This section is Read Only
  SectionIn RO
  
  ; Set output path to the installation directory.
  SetOutPath $INSTDIR
  
  ; Add files recursively from the Fotocop ditribution directory, keeping their file properties 
  File /a /r "${FOTOCOP_DIST}\*"
  
  ; Write the installation path into the registry
  WriteRegStr "${REG_ROOT}" "${REG_APP_PATH}" "Install_Location" "$INSTDIR"
  
  ; Write the uninstall keys for Windows
  WriteRegStr "${REG_ROOT}" "${REG_UNINSTALL_PATH}" "DisplayName" "Fotocop"
  WriteRegStr "${REG_ROOT}" "${REG_UNINSTALL_PATH}" "DisplayIcon" "$INSTDIR\Fotocop.exe,0"
  WriteRegStr "${REG_ROOT}" "${REG_UNINSTALL_PATH}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr "${REG_ROOT}" "${REG_UNINSTALL_PATH}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD "${REG_ROOT}" "${REG_UNINSTALL_PATH}" "NoModify" 1
  WriteRegDWORD "${REG_ROOT}" "${REG_UNINSTALL_PATH}" "NoRepair" 1

  WriteUninstaller "$INSTDIR\Uninstall.exe"
  
SectionEnd

; Optional section (can be disabled by the user)
Section "Start Menu Shortcuts"

  CreateDirectory "$SMPROGRAMS\${NAME}"
  CreateShortcut "$SMPROGRAMS\${NAME}\Uninstall.lnk" "$INSTDIR\uninstall.exe"
  CreateShortcut "$SMPROGRAMS\${NAME}\${NAME}.lnk" "$INSTDIR\Fotocop.exe"

SectionEnd

;--------------------------------

; Uninstaller
; Free adaptation from: https://nsis.sourceforge.io/Uninstall_only_installed_files

Section "Uninstall"

  ;Can't uninstall if uninstall log is missing!
  IfFileExists "$INSTDIR\${UninstLog}" +3
    MessageBox MB_OK|MB_ICONSTOP "$(UninstLogMissing)"
      Abort
 
  Push $R0
  Push $R1
  Push $R2
  ; Open the uninstall log file
  SetFileAttributes "$INSTDIR\${UninstLog}" NORMAL
  FileOpen $UninstLog "$INSTDIR\${UninstLog}" r
  StrCpy $R1 -1
 
  ; Get each file to unistall and their count from the unistall log file
  GetLineCount:
    ClearErrors
    FileRead $UninstLog $R0
    IntOp $R1 $R1 + 1
    StrCpy $R0 $R0 -2 #remove the ending CRLF
    Push $R0   
    IfErrors 0 GetLineCount
 
  Pop $R0
 
  ; Delete each listed file or directory
  LoopRead:
    StrCmp $R1 0 LoopDone
    Pop $R0
 
    IfFileExists "$INSTDIR\$R0\*.*" 0 +3
      RMDir /r "$INSTDIR\$R0"  #is dir
    Goto +3
    IfFileExists "$INSTDIR\$R0" 0 +2
      Delete "$INSTDIR\$R0" #is file
 
    IntOp $R1 $R1 - 1
    Goto LoopRead
  ; Close the uninstall log file
  LoopDone:
  FileClose $UninstLog
  
  ; Remove uninstaller, uninstall log and the install dir
  Delete $INSTDIR\uninstall.exe
  Delete "$INSTDIR\${UninstLog}"
  RMDir "$INSTDIR"
  Pop $R2
  Pop $R1
  Pop $R0
  
  ; Remove registry keys
  DeleteRegKey "${REG_ROOT}" "${REG_UNINSTALL_PATH}"
  DeleteRegKey "${REG_ROOT}" "${REG_APP_PATH}"

  ; Remove shortcuts, if any
  Delete "$SMPROGRAMS\Fotocop\*.lnk"
  RMDir "$SMPROGRAMS\Fotocop"

SectionEnd
