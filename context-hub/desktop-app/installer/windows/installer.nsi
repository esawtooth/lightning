; Context Hub NSIS Installer Script
; Creates a user-friendly Windows installer

!include "MUI2.nsh"
!include "FileFunc.nsh"

; Application info
!define APPNAME "Context Hub"
!define COMPANYNAME "Context Hub Inc"
!define DESCRIPTION "Your AI-powered filesystem in the cloud"
!define VERSIONMAJOR 1
!define VERSIONMINOR 0
!define VERSIONBUILD 0
!define INSTALLSIZE 150000 ; Size in KB

Name "${APPNAME}"
OutFile "ContextHub-Setup.exe"
InstallDir "$PROGRAMFILES64\${APPNAME}"
InstallDirRegKey HKLM "Software\${COMPANYNAME}\${APPNAME}" "InstallDir"

; Request admin privileges
RequestExecutionLevel admin

; Interface settings
!define MUI_ICON "..\..\icons\icon.ico"
!define MUI_UNICON "..\..\icons\icon.ico"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "header.bmp"
!define MUI_WELCOMEFINISHPAGE_BITMAP "welcome.bmp"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY

; Custom page for mount location
Page custom MountLocationPage MountLocationPageLeave

!insertmacro MUI_PAGE_INSTFILES

; Finish page with options
!define MUI_FINISHPAGE_RUN "$INSTDIR\ContextHub.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch Context Hub"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\README.txt"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "View Quick Start Guide"
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Languages
!insertmacro MUI_LANGUAGE "English"

; Custom variables
Var MountPath
Var MountPathTextBox

; Installer sections
Section "Context Hub" MainSection
    SetOutPath $INSTDIR
    
    ; Extract files
    File "..\..\target\release\ContextHub.exe"
    File "..\..\README.txt"
    File "..\..\icons\icon.ico"
    
    ; Install WinFsp (filesystem driver)
    File "winfsp-2.0.msi"
    ExecWait 'msiexec /i "$INSTDIR\winfsp-2.0.msi" /quiet'
    
    ; Create start menu shortcuts
    CreateDirectory "$SMPROGRAMS\${APPNAME}"
    CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\ContextHub.exe" "" "$INSTDIR\icon.ico"
    CreateShortcut "$SMPROGRAMS\${APPNAME}\Uninstall.lnk" "$INSTDIR\uninstall.exe"
    
    ; Create desktop shortcut
    CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\ContextHub.exe" "" "$INSTDIR\icon.ico"
    
    ; Add to system tray startup
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}" "$INSTDIR\ContextHub.exe --minimized"
    
    ; Write registry keys
    WriteRegStr HKLM "Software\${COMPANYNAME}\${APPNAME}" "InstallDir" "$INSTDIR"
    WriteRegStr HKLM "Software\${COMPANYNAME}\${APPNAME}" "MountPath" "$MountPath"
    WriteRegStr HKLM "Software\${COMPANYNAME}\${APPNAME}" "Version" "${VERSIONMAJOR}.${VERSIONMINOR}.${VERSIONBUILD}"
    
    ; Windows uninstaller
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayIcon" "$INSTDIR\icon.ico"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "${COMPANYNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${VERSIONMAJOR}.${VERSIONMINOR}.${VERSIONBUILD}"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "EstimatedSize" ${INSTALLSIZE}
    
    ; Create mount directory
    CreateDirectory "$MountPath"
    
    ; Write uninstaller
    WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

; Custom page functions
Function MountLocationPage
    !insertmacro MUI_HEADER_TEXT "Choose Mount Location" "Select where Context Hub files will appear on your computer"
    
    nsDialogs::Create 1018
    Pop $0
    
    ${NSD_CreateLabel} 0 0 100% 12u "Context Hub will create a folder at this location:"
    Pop $0
    
    ${NSD_CreateText} 0 20u 75% 12u "$DOCUMENTS\Context Hub"
    Pop $MountPathTextBox
    
    ${NSD_CreateButton} 77% 19u 20% 12u "Browse..."
    Pop $0
    ${NSD_OnClick} $0 BrowseForFolder
    
    ${NSD_CreateLabel} 0 40u 100% 24u "This folder will sync with your Context Hub cloud storage. You can access your files here using any application."
    Pop $0
    
    nsDialogs::Show
FunctionEnd

Function BrowseForFolder
    nsDialogs::SelectFolderDialog "Select Context Hub folder location" "$DOCUMENTS"
    Pop $0
    ${If} $0 != error
        ${NSD_SetText} $MountPathTextBox $0
    ${EndIf}
FunctionEnd

Function MountLocationPageLeave
    ${NSD_GetText} $MountPathTextBox $MountPath
FunctionEnd

; Uninstaller
Section "Uninstall"
    ; Stop the application
    ExecWait 'taskkill /F /IM ContextHub.exe'
    
    ; Remove from startup
    DeleteRegValue HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}"
    
    ; Delete files
    Delete "$INSTDIR\ContextHub.exe"
    Delete "$INSTDIR\README.txt"
    Delete "$INSTDIR\icon.ico"
    Delete "$INSTDIR\winfsp-2.0.msi"
    Delete "$INSTDIR\uninstall.exe"
    
    ; Remove shortcuts
    Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
    Delete "$SMPROGRAMS\${APPNAME}\Uninstall.lnk"
    RMDir "$SMPROGRAMS\${APPNAME}"
    Delete "$DESKTOP\${APPNAME}.lnk"
    
    ; Remove registry keys
    DeleteRegKey HKLM "Software\${COMPANYNAME}\${APPNAME}"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
    
    ; Remove installation directory
    RMDir "$INSTDIR"
    
    ; Ask about removing mount directory
    MessageBox MB_YESNO "Do you want to remove your Context Hub files at $MountPath?" IDNO +2
    RMDir /r "$MountPath"
SectionEnd