use std::fs::{self, OpenOptions};
use std::io;
use std::net::{SocketAddr, TcpListener};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tauri::{AppHandle, Manager};
use url::{Host, Url};
use uuid::Uuid;

const AGENT_RUNTIME_SCHEMA: &str = "loopforge-agent-runtime-v1";
const MAX_AGENT_ERROR_BYTES: usize = 4096;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct AgentRuntimeMetadata {
    schema_version: String,
    bind_addr: String,
    token: String,
    project_root: String,
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
    root.join(".loopforge")
        .join("agent")
        .join("loopforge-runtime.json")
}

fn log_path(root: &Path) -> PathBuf {
    root.join(".loopforge")
        .join("agent")
        .join("logs")
        .join("loopforge-agent.log")
}

fn bundled_binary(app: &AppHandle, environment_name: &str, binary_name: &str) -> Option<String> {
    if let Ok(path) = std::env::var(environment_name) {
        if Path::new(&path).is_file() {
            return Some(path);
        }
    }
    let resource_dir = app.path().resource_dir().ok()?;
    [
        resource_dir.join("resources").join(binary_name),
        resource_dir.join(binary_name),
    ]
    .into_iter()
    .find(|path| path.is_file())
    .map(|path| path.to_string_lossy().into_owned())
}

fn bundled_agent_binary(app: &AppHandle) -> Option<String> {
    let name = if cfg!(windows) {
        "loopforge-agent.exe"
    } else {
        "loopforge-agent"
    };
    bundled_binary(app, "LOOPFORGE_AGENT_BIN", name)
}

fn bundled_kura_binary(app: &AppHandle) -> Option<String> {
    if let Ok(path) =
        std::env::var("LOOPFORGE_KURA_BIN").or_else(|_| std::env::var("LOOPFORGE_DOPE_BIN"))
    {
        if Path::new(&path).is_file() {
            return Some(path);
        }
    }
    let name = if cfg!(windows) {
        "dope-cli.exe"
    } else {
        "dope-cli"
    };
    bundled_binary(app, "LOOPFORGE_KURA_BIN", name)
}

fn validate_runtime(root: &Path, metadata: &AgentRuntimeMetadata) -> Result<(), String> {
    if metadata.schema_version != AGENT_RUNTIME_SCHEMA {
        return Err("Loopforge Agent metadata has an unsupported schema version".to_string());
    }
    let address: SocketAddr = metadata
        .bind_addr
        .parse()
        .map_err(|_| "Loopforge Agent metadata has an invalid bind address".to_string())?;
    if !address.ip().is_loopback() || address.port() == 0 {
        return Err("Loopforge Agent metadata must use a loopback port".to_string());
    }
    if metadata.token.len() < 32 {
        return Err("Loopforge Agent metadata has an invalid token".to_string());
    }
    if Path::new(&metadata.project_root) != root {
        return Err("Loopforge Agent metadata belongs to another project".to_string());
    }
    Ok(())
}

fn load_runtime(root: &Path) -> Result<Option<AgentRuntimeMetadata>, String> {
    let path = runtime_path(root);
    if !path.is_file() {
        return Ok(None);
    }
    let metadata: AgentRuntimeMetadata = serde_json::from_slice(
        &fs::read(&path)
            .map_err(|error| format!("cannot read Loopforge Agent metadata: {error}"))?,
    )
    .map_err(|error| format!("Loopforge Agent metadata is invalid: {error}"))?;
    validate_runtime(root, &metadata)?;
    Ok(Some(metadata))
}

fn save_runtime(root: &Path, metadata: &AgentRuntimeMetadata) -> Result<(), String> {
    validate_runtime(root, metadata)?;
    let path = runtime_path(root);
    let parent = path
        .parent()
        .ok_or_else(|| "runtime path has no parent".to_string())?;
    fs::create_dir_all(parent)
        .map_err(|error| format!("cannot create Agent runtime directory: {error}"))?;
    let temporary = path.with_extension("json.tmp");
    fs::write(
        &temporary,
        serde_json::to_vec_pretty(metadata).map_err(|error| error.to_string())?,
    )
    .map_err(|error| format!("cannot write Agent runtime metadata: {error}"))?;
    secure_file(&temporary).map_err(|error| format!("cannot secure Agent metadata: {error}"))?;
    fs::rename(temporary, path)
        .map_err(|error| format!("cannot commit Agent runtime metadata: {error}"))
}

#[cfg(unix)]
fn secure_file(path: &Path) -> io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))
}

#[cfg(not(unix))]
fn secure_file(_path: &Path) -> io::Result<()> {
    Ok(())
}

fn agent_url(metadata: &AgentRuntimeMetadata, path: &str) -> Result<String, String> {
    let mut base = Url::parse(&format!("http://{}", metadata.bind_addr))
        .map_err(|_| "Loopforge Agent URL is invalid".to_string())?;
    let loopback = matches!(base.host(), Some(Host::Domain("localhost")))
        || matches!(base.host(), Some(Host::Ipv4(address)) if address.is_loopback())
        || matches!(base.host(), Some(Host::Ipv6(address)) if address.is_loopback());
    if !loopback || base.port().is_none() || !path.starts_with('/') || path.starts_with("//") {
        return Err("Loopforge Agent URL must use an absolute loopback path".to_string());
    }
    if path.contains(['?', '#']) {
        return Err("Loopforge Agent path must not contain a query or fragment".to_string());
    }
    base.set_path(path);
    Ok(base.into())
}

fn agent_request(
    metadata: &AgentRuntimeMetadata,
    method: &str,
    path: &str,
    body: Option<Value>,
    timeout: Duration,
) -> Result<Value, String> {
    let url = agent_url(metadata, path)?;
    let authorization = format!("Bearer {}", metadata.token);
    let response = match method {
        "GET" => ureq::get(&url)
            .set("Authorization", &authorization)
            .timeout(timeout)
            .call(),
        "POST" => ureq::post(&url)
            .set("Authorization", &authorization)
            .timeout(timeout)
            .send_json(body.unwrap_or_else(|| json!({}))),
        _ => return Err("unsupported Agent request method".to_string()),
    };
    response
        .map_err(|error| format!("Loopforge Agent request failed: {error}"))?
        .into_json()
        .map_err(|error| format!("Loopforge Agent returned invalid JSON: {error}"))
}

fn command_error(stderr: &[u8]) -> String {
    let end = stderr.len().min(MAX_AGENT_ERROR_BYTES);
    let message = String::from_utf8_lossy(&stderr[..end]);
    if stderr.len() > end {
        format!("{}... (truncated)", message.trim())
    } else {
        message.trim().to_string()
    }
}

fn agent_status_for_root(root: &Path) -> Result<Value, String> {
    let Some(metadata) = load_runtime(root)? else {
        return Ok(json!({
            "schema_version": "loopforge-agent-status-v1",
            "ready": false,
            "managed": false
        }));
    };
    match agent_request(&metadata, "GET", "/v1/status", None, Duration::from_secs(2)) {
        Ok(mut status) => {
            if let Some(object) = status.as_object_mut() {
                object.insert("managed".to_string(), Value::Bool(true));
            }
            Ok(status)
        }
        Err(reason) => Ok(json!({
            "schema_version": "loopforge-agent-status-v1",
            "ready": false,
            "managed": true,
            "reason": reason
        })),
    }
}

#[tauri::command]
fn agent_status(project_path: String) -> Result<Value, String> {
    agent_status_for_root(&project_root(&project_path)?)
}

#[tauri::command]
fn agent_start(app: AppHandle, project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let current = agent_status_for_root(&root)?;
    if current.get("ready").and_then(Value::as_bool) == Some(true) {
        return Ok(current);
    }
    if current.get("managed").and_then(Value::as_bool) == Some(true) {
        return Err(format!(
            "Loopforge Agent metadata exists but the Agent is unreachable; inspect {} before recovery",
            runtime_path(&root).display()
        ));
    }
    let agent_binary = bundled_agent_binary(&app).ok_or_else(|| {
        "Loopforge Agent sidecar is missing; run pnpm build:agent or set LOOPFORGE_AGENT_BIN"
            .to_string()
    })?;
    let kura_binary = bundled_kura_binary(&app).ok_or_else(|| {
        "Kura runtime is missing; run pnpm build:kura or set LOOPFORGE_KURA_BIN".to_string()
    })?;
    let listener = TcpListener::bind("127.0.0.1:0")
        .map_err(|error| format!("cannot reserve a local Agent port: {error}"))?;
    let port = listener
        .local_addr()
        .map_err(|error| error.to_string())?
        .port();
    drop(listener);
    let metadata = AgentRuntimeMetadata {
        schema_version: AGENT_RUNTIME_SCHEMA.to_string(),
        bind_addr: format!("127.0.0.1:{port}"),
        token: format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple()),
        project_root: root.to_string_lossy().into_owned(),
    };
    let path = log_path(&root);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create Agent log directory: {error}"))?;
    }
    let stdout = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|error| format!("cannot open Agent log: {error}"))?;
    let stderr = stdout
        .try_clone()
        .map_err(|error| format!("cannot clone Agent log handle: {error}"))?;
    let mut child = Command::new(&agent_binary)
        .args([
            "serve",
            "--project",
            &metadata.project_root,
            "--host",
            "127.0.0.1",
            "--port",
            &port.to_string(),
            "--token",
            &metadata.token,
            "--kura-binary",
            &kura_binary,
        ])
        .current_dir(&root)
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .spawn()
        .map_err(|error| format!("failed to start Loopforge Agent: {error}"))?;
    if let Err(error) = save_runtime(&root, &metadata) {
        let _ = child.kill();
        return Err(error);
    }
    for _ in 0..50 {
        if agent_request(
            &metadata,
            "GET",
            "/healthz",
            None,
            Duration::from_millis(500),
        )
        .is_ok()
        {
            let mut status = agent_request(
                &metadata,
                "POST",
                "/v1/start",
                Some(json!({})),
                Duration::from_secs(15),
            )?;
            if let Some(object) = status.as_object_mut() {
                object.insert("managed".to_string(), Value::Bool(true));
            }
            return Ok(status);
        }
        if child
            .try_wait()
            .map_err(|error| format!("cannot inspect Loopforge Agent: {error}"))?
            .is_some()
        {
            break;
        }
        thread::sleep(Duration::from_millis(200));
    }
    let _ = child.kill();
    let _ = fs::remove_file(runtime_path(&root));
    let log_tail = fs::read(&path).unwrap_or_default();
    Err(format!(
        "Loopforge Agent did not become ready: {}",
        command_error(&log_tail)
    ))
}

#[tauri::command]
fn agent_stop(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let Some(metadata) = load_runtime(&root)? else {
        return Ok(json!({
            "schema_version": "loopforge-agent-status-v1",
            "ready": false,
            "managed": false
        }));
    };
    let result = agent_request(
        &metadata,
        "POST",
        "/v1/shutdown",
        Some(json!({})),
        Duration::from_secs(15),
    )?;
    fs::remove_file(runtime_path(&root))
        .map_err(|error| format!("Agent stopped but runtime metadata remains: {error}"))?;
    Ok(result)
}

#[tauri::command]
fn agent_query(
    project_path: String,
    query: String,
    thread_id: Option<String>,
) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/query",
        Some(json!({"query": query, "thread_id": thread_id})),
        Duration::from_secs(120),
    )
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            agent_status,
            agent_start,
            agent_stop,
            agent_query
        ])
        .run(tauri::generate_context!())
        .expect("error while running Loopforge Workbench");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temporary_root(name: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "loopforge-workbench-{name}-{}-{}",
            std::process::id(),
            Uuid::new_v4()
        ));
        fs::create_dir_all(&root).unwrap();
        root
    }

    fn metadata(root: &Path) -> AgentRuntimeMetadata {
        AgentRuntimeMetadata {
            schema_version: AGENT_RUNTIME_SCHEMA.into(),
            bind_addr: "127.0.0.1:43210".into(),
            token: "a".repeat(64),
            project_root: root.to_string_lossy().into_owned(),
        }
    }

    #[test]
    fn runtime_metadata_round_trip_is_project_scoped() {
        let root = temporary_root("runtime");
        let value = metadata(&root);
        save_runtime(&root, &value).unwrap();
        assert_eq!(load_runtime(&root).unwrap(), Some(value));
        let other = temporary_root("other");
        assert!(validate_runtime(&other, &metadata(&root)).is_err());
        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_dir_all(other);
    }

    #[test]
    fn rejects_non_loopback_or_weak_runtime_metadata() {
        let root = temporary_root("tampered");
        let mut value = metadata(&root);
        value.bind_addr = "10.0.0.1:43210".into();
        assert!(validate_runtime(&root, &value).is_err());
        value.bind_addr = "127.0.0.1:43210".into();
        value.token = "weak".into();
        assert!(validate_runtime(&root, &value).is_err());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn agent_urls_are_loopback_and_path_constrained() {
        let root = temporary_root("url");
        let value = metadata(&root);
        assert_eq!(
            agent_url(&value, "/v1/status").unwrap(),
            "http://127.0.0.1:43210/v1/status"
        );
        assert!(agent_url(&value, "v1/status").is_err());
        assert!(agent_url(&value, "//evil.example").is_err());
        assert!(agent_url(&value, "/v1/status?token=x").is_err());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn truncates_sidecar_errors() {
        let stderr = vec![b'x'; MAX_AGENT_ERROR_BYTES + 1];
        let message = command_error(&stderr);
        assert!(message.ends_with("... (truncated)"));
        assert!(message.len() < stderr.len() + 20);
    }
}
