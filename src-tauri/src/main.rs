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

use std::fs::OpenOptions;
use std::io::{BufRead, BufReader};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::Duration;

use tauri::Emitter;

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

/// Nutzerspezifischer Datenordner -- identisch zu config.data_dir() im Backend,
/// damit GUI und Backend dieselben Dateien (z.B. das Startup-Log) nutzen.
fn data_dir() -> PathBuf {
    #[cfg(windows)]
    let base = std::env::var("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|_| {
            PathBuf::from(std::env::var("USERPROFILE").unwrap_or_default())
                .join("AppData")
                .join("Roaming")
        });
    #[cfg(target_os = "macos")]
    let base = PathBuf::from(std::env::var("HOME").unwrap_or_default())
        .join("Library")
        .join("Application Support");
    #[cfg(all(unix, not(target_os = "macos")))]
    let base = std::env::var("XDG_DATA_HOME").map(PathBuf::from).unwrap_or_else(|_| {
        PathBuf::from(std::env::var("HOME").unwrap_or_default())
            .join(".local")
            .join("share")
    });

    let dir = base.join("PrivacyAgent");
    let _ = std::fs::create_dir_all(&dir);
    dir
}

/// Prueft, ob bereits ein Backend auf 127.0.0.1:8765 lauscht.
fn backend_running() -> bool {
    match "127.0.0.1:8765".parse::<std::net::SocketAddr>() {
        Ok(addr) => TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok(),
        Err(_) => false,
    }
}

/// Startet das Backend (Modus "serve") im Hintergrund -- aber NUR, wenn nicht
/// schon eines laeuft (verhindert Doppelstart / Port-Konflikt). Die Start-
/// Ausgabe wird in <Datenordner>/backend-start.log umgeleitet (Diagnose).
fn spawn_backend() {
    if backend_running() {
        return; // Es laeuft bereits eines -- kein zweites starten.
    }
    let mut cmd = Command::new(sidecar_path());
    cmd.arg("serve");

    // stdout/stderr in eine bei jedem Start frische Logdatei schreiben.
    let log_path = data_dir().join("backend-start.log");
    match OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&log_path)
        .and_then(|f| f.try_clone().map(|f2| (f, f2)))
    {
        Ok((out, err)) => {
            cmd.stdout(Stdio::from(out)).stderr(Stdio::from(err));
        }
        Err(_) => {
            cmd.stdout(Stdio::null()).stderr(Stdio::null());
        }
    }

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
