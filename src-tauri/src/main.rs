// Tauri-Huelle des Privacy-Agenten.
//
// Aufgaben:
//   * Beim Start das gebuendelte Python-Backend (Sidecar) im Modus "serve"
//     starten -- KEIN System-Python noetig, der Interpreter steckt im Binary.
//   * Den Einrichtungs-Assistenten (Modus "setup") ausfuehren und dessen
//     Fortschritt als Events ("setup-progress") an die GUI weiterreichen.
//
// Das Sidecar-Binary wird von build_sidecar.py erzeugt und liegt zur Laufzeit
// (sowohl bei `tauri dev` als auch im fertigen Bundle) direkt neben der
// App-Executable -- Tauri kopiert externalBin dorthin und entfernt dabei das
// Target-Triple aus dem Namen.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Command, Stdio};

use tauri::{Emitter, Manager};

#[cfg(windows)]
use std::os::windows::process::CommandExt;
/// Verhindert das Aufpoppen eines Konsolenfensters (Windows).
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// Setzt das Fensterlos-Flag plattformabhaengig.
fn hide_window(cmd: &mut Command) {
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    let _ = cmd; // auf Nicht-Windows ungenutzt
}

/// Voller Pfad zum Sidecar-Binary neben der laufenden App-Executable.
fn sidecar_path() -> PathBuf {
    let mut dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(PathBuf::from))
        .unwrap_or_default();
    let name = if cfg!(target_os = "windows") {
        "privacy-agent-backend.exe"
    } else {
        "privacy-agent-backend"
    };
    dir.push(name);
    dir
}

/// Startet das Backend (Modus "serve") im Hintergrund.
fn spawn_backend() {
    let mut cmd = Command::new(sidecar_path());
    cmd.arg("serve").stdout(Stdio::null()).stderr(Stdio::null());
    hide_window(&mut cmd);
    let _ = cmd.spawn();
}

/// Fuehrt den Einrichtungs-Assistenten (Modus "setup") aus und streamt den
/// Fortschritt zeilenweise als "setup-progress"-Events an die GUI.
#[tauri::command]
async fn run_setup(app: tauri::AppHandle) -> Result<(), String> {
    let mut cmd = Command::new(sidecar_path());
    cmd.arg("setup").stdout(Stdio::piped()).stderr(Stdio::piped());
    hide_window(&mut cmd);
    let mut child = cmd
        .spawn()
        .map_err(|e| format!("Konnte Einrichtung nicht starten: {e}"))?;

    let stdout = child.stdout.take().ok_or("Kein stdout")?;
    let reader = BufReader::new(stdout);

    for line in reader.lines() {
        let line = line.map_err(|e| e.to_string())?;
        // Jede Zeile ist ein JSON-Fortschrittsobjekt aus first_run.py.
        if let Ok(value) = serde_json::from_str::<serde_json::Value>(&line) {
            let _ = app.emit("setup-progress", value);
        }
    }

    let status = child.wait().map_err(|e| e.to_string())?;
    if status.success() {
        Ok(())
    } else {
        Err("Einrichtung fehlgeschlagen.".into())
    }
}

fn main() {
    tauri::Builder::default()
        .setup(|_app| {
            spawn_backend();
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![run_setup])
        .run(tauri::generate_context!())
        .expect("Fehler beim Start der Tauri-Anwendung");
}
