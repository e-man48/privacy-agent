; Installer-Hooks fuer den Windows-Installer (NSIS).
; Beenden die laufenden Prozesse VOR der (Neu-)Installation bzw. Deinstallation,
; damit kein Rechner-Neustart noetig ist (sonst sperrt das laufende Backend die
; eigene .exe und der Installer kann sie nicht ueberschreiben).

!macro NSIS_HOOK_PREINSTALL
  DetailPrint "Beende laufenden Hintergrundprozess ..."
  nsExec::Exec 'taskkill /F /T /IM "privacy-agent-backend.exe"'
  nsExec::Exec 'taskkill /F /T /IM "Privacy-Agent.exe"'
  Sleep 800
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::Exec 'taskkill /F /T /IM "privacy-agent-backend.exe"'
  nsExec::Exec 'taskkill /F /T /IM "Privacy-Agent.exe"'
  Sleep 500
!macroend
