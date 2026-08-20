use std::fs;
use std::net::{SocketAddr, TcpListener};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::thread;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tauri::{AppHandle, Manager};
use url::{Host, Url};

const MAX_DAEMON_ERROR_BYTES: usize = 4096;
const MAX_PROJECT_CONTEXT_BYTES: usize = 64 * 1024;

fn bundled_dope_binary(app: &AppHandle) -> Option<String> {
    if let Ok(path) =
        std::env::var("LOOPFORGE_KURA_BIN").or_else(|_| std::env::var("LOOPFORGE_DOPE_BIN"))
    {
        if Path::new(&path).is_file() {
            return Some(path);
        }
    }
    let resource_dir = app.path().resource_dir().ok()?;
    let binary_name = if cfg!(windows) {
        "dope-cli.exe"
    } else {
        "dope-cli"
    };
    [
        resource_dir.join("resources").join(binary_name),
        resource_dir.join(binary_name),
    ]
    .into_iter()
    .find(|path| path.is_file())
    .map(|path| path.to_string_lossy().into_owned())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct RuntimeMetadata {
    schema_version: String,
    bind_addr: String,
    data_dir: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct LoopforgeProjectContext {
    schema_version: String,
    project_id: String,
    project_root: String,
    observed_revision: u64,
    stage: String,
    engine: Option<String>,
    capabilities: Vec<String>,
    next_actions: Vec<String>,
    redactions: Vec<String>,
}

fn project_root(path: &str) -> Result<PathBuf, String> {
    let root = PathBuf::from(path);
    if path.trim().is_empty() || !root.is_dir() {
        return Err("project root must be an existing directory".to_string());
    }
    root.canonicalize()
        .map_err(|error| format!("cannot resolve project root: {error}"))
}

fn runtime_path(root: &Path) -> PathBuf {
    root.join(".loopforge").join("agent").join("runtime.json")
}

fn project_context_path(root: &Path) -> PathBuf {
    root.join(".loopforge").join("agent").join("context.json")
}

fn load_project_context(root: &Path) -> Result<LoopforgeProjectContext, String> {
    let path = project_context_path(root);
    let bytes = fs::read(&path)
        .map_err(|error| format!("cannot read Loopforge project context: {error}"))?;
    if bytes.len() > MAX_PROJECT_CONTEXT_BYTES {
        return Err("Loopforge project context exceeds the size limit".to_string());
    }
    let context: LoopforgeProjectContext = serde_json::from_slice(&bytes)
        .map_err(|error| format!("Loopforge project context is invalid: {error}"))?;
    if context.schema_version != "game-project-context-v1"
        || context.project_id.trim().is_empty()
        || context.stage.trim().is_empty()
        || Path::new(&context.project_root) != root
    {
        return Err("Loopforge project context failed validation".to_string());
    }
    Ok(context)
}

fn load_runtime(root: &Path) -> Result<Option<RuntimeMetadata>, String> {
    let path = runtime_path(root);
    if !path.is_file() {
        return Ok(None);
    }
    let bytes =
        fs::read(path).map_err(|error| format!("cannot read Kura runtime metadata: {error}"))?;
    let metadata: RuntimeMetadata = serde_json::from_slice(&bytes)
        .map_err(|error| format!("Kura runtime metadata is invalid: {error}"))?;
    validate_runtime(root, &metadata)?;
    Ok(Some(metadata))
}

fn validate_runtime(root: &Path, metadata: &RuntimeMetadata) -> Result<(), String> {
    if metadata.schema_version != "kura-runtime-v1" {
        return Err("Kura runtime metadata has an unsupported schema version".to_string());
    }
    let address: SocketAddr = metadata
        .bind_addr
        .parse()
        .map_err(|_| "Kura runtime metadata has an invalid bind address".to_string())?;
    if !address.ip().is_loopback() || address.port() == 0 {
        return Err("Kura runtime metadata must use a loopback port".to_string());
    }
    let expected_data_dir = root.join(".loopforge").join("agent").join("data");
    if Path::new(&metadata.data_dir) != expected_data_dir {
        return Err("Kura runtime metadata references an unexpected data directory".to_string());
    }
    Ok(())
}

fn save_runtime(root: &Path, metadata: &RuntimeMetadata) -> Result<(), String> {
    let path = runtime_path(root);
    let parent = path
        .parent()
        .ok_or_else(|| "runtime path has no parent".to_string())?;
    fs::create_dir_all(parent)
        .map_err(|error| format!("cannot create runtime directory: {error}"))?;
    let temporary = path.with_extension("json.tmp");
    let bytes = serde_json::to_vec_pretty(metadata).map_err(|error| error.to_string())?;
    fs::write(&temporary, bytes)
        .map_err(|error| format!("cannot write runtime metadata: {error}"))?;
    fs::rename(temporary, path).map_err(|error| format!("cannot commit runtime metadata: {error}"))
}

fn daemon_json(base_url: &str, path: &str) -> Result<Value, String> {
    ureq::get(&daemon_url(base_url, path)?)
        .timeout(Duration::from_secs(2))
        .call()
        .map_err(|error| format!("Kura request failed: {error}"))?
        .into_json()
        .map_err(|error| format!("Kura returned invalid JSON: {error}"))
}

fn command_error(stderr: &[u8]) -> String {
    let end = stderr.len().min(MAX_DAEMON_ERROR_BYTES);
    let message = String::from_utf8_lossy(&stderr[..end]);
    if stderr.len() > end {
        format!("{}... (truncated)", message.trim())
    } else {
        message.trim().to_string()
    }
}

fn runtime_status(root: &Path) -> Result<Value, String> {
    let Some(metadata) = load_runtime(root)? else {
        return Ok(json!({"running": false, "healthy": false, "managed": false}));
    };
    let base_url = format!("http://{}", metadata.bind_addr);
    match daemon_json(&base_url, "/healthz") {
        Ok(health) => Ok(json!({
            "running": true,
            "healthy": health.get("ok").and_then(Value::as_bool).unwrap_or(false),
            "managed": true,
            "base_url": base_url,
            "health": health,
            "version": daemon_json(&base_url, "/version").ok()
        })),
        Err(error) => Ok(json!({
            "running": false,
            "healthy": false,
            "managed": true,
            "base_url": base_url,
            "reason": error
        })),
    }
}

#[tauri::command]
fn agent_status(project_path: String) -> Result<Value, String> {
    runtime_status(&project_root(&project_path)?)
}

#[tauri::command]
fn project_context(project_path: String) -> Result<LoopforgeProjectContext, String> {
    load_project_context(&project_root(&project_path)?)
}

#[tauri::command]
fn agent_start(app: AppHandle, project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let current = runtime_status(&root)?;
    if current.get("healthy").and_then(Value::as_bool) == Some(true) {
        return Ok(current);
    }
    let binary = bundled_dope_binary(&app).ok_or_else(|| {
        "bundled Kura daemon is missing; rebuild the desktop package or set LOOPFORGE_KURA_BIN"
            .to_string()
    })?;
    let listener = TcpListener::bind("127.0.0.1:0")
        .map_err(|error| format!("cannot reserve a local Kura port: {error}"))?;
    let port = listener
        .local_addr()
        .map_err(|error| error.to_string())?
        .port();
    drop(listener);
    let bind_addr = format!("127.0.0.1:{port}");
    let data_dir = root.join(".loopforge").join("agent").join("data");
    let output = Command::new(&binary)
        .args(["daemon", "start"])
        .current_dir(&root)
        .env("DOPE_ENV", "test")
        .env("DOPE_DATA_DIR", &data_dir)
        .env("DOPE_BIND_ADDR", &bind_addr)
        .output()
        .map_err(|error| format!("failed to start bundled Kura: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "Kura failed to start: {}",
            command_error(&output.stderr)
        ));
    }
    let metadata = RuntimeMetadata {
        schema_version: "kura-runtime-v1".to_string(),
        bind_addr: bind_addr.clone(),
        data_dir: data_dir.to_string_lossy().into_owned(),
    };
    if let Err(error) = save_runtime(&root, &metadata) {
        let _ = Command::new(&binary)
            .args(["daemon", "stop"])
            .current_dir(&root)
            .env("DOPE_ENV", "test")
            .env("DOPE_DATA_DIR", &metadata.data_dir)
            .env("DOPE_BIND_ADDR", &metadata.bind_addr)
            .output();
        return Err(error);
    }
    for _ in 0..50 {
        let status = runtime_status(&root)?;
        if status.get("healthy").and_then(Value::as_bool) == Some(true) {
            return Ok(status);
        }
        thread::sleep(Duration::from_millis(200));
    }
    let _ = Command::new(&binary)
        .args(["daemon", "stop"])
        .current_dir(&root)
        .env("DOPE_ENV", "test")
        .env("DOPE_DATA_DIR", &metadata.data_dir)
        .env("DOPE_BIND_ADDR", &metadata.bind_addr)
        .output();
    let _ = fs::remove_file(runtime_path(&root));
    Err("Kura did not become healthy within 10 seconds".to_string())
}

#[tauri::command]
fn agent_stop(app: AppHandle, project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let Some(metadata) = load_runtime(&root)? else {
        return Ok(json!({"running": false, "healthy": false, "stopped": false}));
    };
    let binary =
        bundled_dope_binary(&app).ok_or_else(|| "bundled Kura daemon is missing".to_string())?;
    let output = Command::new(binary)
        .args(["daemon", "stop"])
        .current_dir(&root)
        .env("DOPE_ENV", "test")
        .env("DOPE_DATA_DIR", &metadata.data_dir)
        .env("DOPE_BIND_ADDR", &metadata.bind_addr)
        .output()
        .map_err(|error| format!("failed to stop bundled Kura: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "Kura failed to stop: {}",
            command_error(&output.stderr)
        ));
    }
    let _ = fs::remove_file(runtime_path(&root));
    Ok(json!({"running": false, "healthy": false, "stopped": true}))
}

fn daemon_url(base_url: &str, path: &str) -> Result<String, String> {
    let mut base = Url::parse(base_url.trim())
        .map_err(|_| "daemon URL must be a valid loopback HTTP URL".to_string())?;
    let loopback = matches!(base.host(), Some(Host::Domain("localhost")))
        || matches!(base.host(), Some(Host::Ipv4(address)) if address.is_loopback())
        || matches!(base.host(), Some(Host::Ipv6(address)) if address.is_loopback());
    if base.scheme() != "http"
        || !loopback
        || !base.username().is_empty()
        || base.password().is_some()
        || base.port().is_none()
    {
        return Err("daemon URL must use a loopback HTTP address".to_string());
    }
    if base.path() != "/" || base.query().is_some() || base.fragment().is_some() {
        return Err("daemon base URL must not contain a path, query, or fragment".to_string());
    }
    if !path.starts_with('/') || path.starts_with("//") || path.contains(['?', '#']) {
        return Err("daemon path must be absolute".to_string());
    }
    base.set_path(path);
    Ok(base.into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn runtime_metadata_round_trip() {
        let root =
            std::env::temp_dir().join(format!("loopforge-supervisor-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let metadata = RuntimeMetadata {
            schema_version: "kura-runtime-v1".into(),
            bind_addr: "127.0.0.1:43210".into(),
            data_dir: root
                .join(".loopforge")
                .join("agent")
                .join("data")
                .to_string_lossy()
                .into_owned(),
        };
        save_runtime(&root, &metadata).unwrap();
        assert_eq!(
            load_runtime(&root).unwrap().unwrap().bind_addr,
            metadata.bind_addr
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn rejects_non_loopback_daemon_urls() {
        assert!(daemon_url("http://192.168.1.5:8080", "/healthz").is_err());
        assert!(daemon_url("http://127.0.0.1:8080@evil.example", "/healthz").is_err());
        assert!(daemon_url("https://127.0.0.1:8080", "/healthz").is_err());
        assert!(daemon_url("http://127.0.0.1:8080", "healthz").is_err());
        assert_eq!(
            daemon_url("http://127.0.0.1:8080/", "/healthz").unwrap(),
            "http://127.0.0.1:8080/healthz"
        );
    }

    #[test]
    fn truncates_command_errors() {
        let stderr = vec![b'x'; MAX_DAEMON_ERROR_BYTES + 1];
        let message = command_error(&stderr);
        assert!(message.ends_with("... (truncated)"));
        assert!(message.len() < stderr.len() + 20);
    }

    #[test]
    fn rejects_tampered_runtime_metadata() {
        let root = std::env::temp_dir().join(format!(
            "loopforge-supervisor-tampered-{}",
            std::process::id()
        ));
        fs::create_dir_all(&root).unwrap();
        let metadata = RuntimeMetadata {
            schema_version: "kura-runtime-v1".into(),
            bind_addr: "10.0.0.1:43210".into(),
            data_dir: root.join("data").to_string_lossy().into_owned(),
        };
        assert!(validate_runtime(&root, &metadata).is_err());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn missing_runtime_stop_state_is_idempotent() {
        let root = std::env::temp_dir().join(format!(
            "loopforge-supervisor-missing-{}",
            std::process::id()
        ));
        fs::create_dir_all(&root).unwrap();
        assert!(load_runtime(&root).unwrap().is_none());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn project_context_is_loopforge_owned_and_project_scoped() {
        let root =
            std::env::temp_dir().join(format!("loopforge-project-context-{}", std::process::id()));
        let agent_root = root.join(".loopforge").join("agent");
        fs::create_dir_all(&agent_root).unwrap();
        let context = LoopforgeProjectContext {
            schema_version: "game-project-context-v1".into(),
            project_id: "gameproj_test".into(),
            project_root: root.to_string_lossy().into_owned(),
            observed_revision: 3,
            stage: "PROTOTYPING".into(),
            engine: Some("godot".into()),
            capabilities: vec!["loopforge.status".into()],
            next_actions: vec!["run build".into()],
            redactions: vec!["access_tokens".into()],
        };
        fs::write(
            project_context_path(&root),
            serde_json::to_vec(&context).unwrap(),
        )
        .unwrap();

        assert_eq!(load_project_context(&root).unwrap(), context);
        let other_root = root.join("other");
        let other_agent_root = other_root.join(".loopforge").join("agent");
        fs::create_dir_all(&other_agent_root).unwrap();
        fs::write(
            project_context_path(&other_root),
            serde_json::to_vec(&context).unwrap(),
        )
        .unwrap();
        assert!(load_project_context(&other_root).is_err());
        let _ = fs::remove_dir_all(root);
    }
}

#[tauri::command]
fn daemon_get(base_url: String, path: String) -> Result<Value, String> {
    let url = daemon_url(&base_url, &path)?;
    ureq::get(&url)
        .timeout(std::time::Duration::from_secs(5))
        .call()
        .map_err(|error| format!("daemon GET failed: {error}"))?
        .into_json()
        .map_err(|error| format!("daemon returned invalid JSON: {error}"))
}

#[tauri::command]
fn daemon_post(base_url: String, path: String, body: Value) -> Result<Value, String> {
    let url = daemon_url(&base_url, &path)?;
    ureq::post(&url)
        .timeout(std::time::Duration::from_secs(120))
        .send_json(body)
        .map_err(|error| format!("daemon POST failed: {error}"))?
        .into_json()
        .map_err(|error| format!("daemon returned invalid JSON: {error}"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            agent_status,
            project_context,
            agent_start,
            agent_stop,
            daemon_get,
            daemon_post
        ])
        .run(tauri::generate_context!())
        .expect("error while running Loopforge Workbench");
}
