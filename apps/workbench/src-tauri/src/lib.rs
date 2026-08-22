use std::fs::{self, OpenOptions};
use std::io;
use std::io::{BufRead, BufReader};
use std::net::{SocketAddr, TcpListener};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_dialog::DialogExt;
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
    // Kura's binary was renamed from `dope-cli` to `kura`; the old name is
    // still checked so an existing bundle keeps working.
    let names: [&str; 2] = if cfg!(windows) {
        ["kura.exe", "dope-cli.exe"]
    } else {
        ["kura", "dope-cli"]
    };
    names
        .into_iter()
        .find_map(|name| bundled_binary(app, "LOOPFORGE_KURA_BIN", name))
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
async fn select_project_directory(app: AppHandle) -> Result<Option<String>, String> {
    let Some(selection) = app
        .dialog()
        .file()
        .set_title("Add a Loopforge project")
        .blocking_pick_folder()
    else {
        return Ok(None);
    };
    let selected = selection
        .into_path()
        .map_err(|error| format!("selected project is not a local directory: {error}"))?;
    let selected = selected
        .to_str()
        .ok_or_else(|| "selected project path is not valid UTF-8".to_string())?;
    let selected = project_root(selected)?;
    let selected = selected
        .to_str()
        .ok_or_else(|| "resolved project path is not valid UTF-8".to_string())?;
    Ok(Some(selected.to_string()))
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

/// Reads the generic provider inventory the Agent projects from Kura. Model
/// routing and credentials are runtime capabilities, so this is read-only and
/// the Workbench never reaches Kura directly.
#[tauri::command]
fn agent_providers(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/providers",
        None,
        Duration::from_secs(15),
    )
}

/// Reads the Agent's projection of the runtime's chat sessions.
#[tauri::command]
fn agent_sessions(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/sessions",
        None,
        Duration::from_secs(15),
    )
}

/// Streams a reply, emitting one Tauri event per chunk.
///
/// A Tauri command is request/response, so the stream cannot be its return
/// value: the reply is delivered as `agent://stream` events carrying the
/// caller's `stream_id`, and the command returns once the run ends. Each event
/// names its kind so the UI can distinguish partial text from completion and
/// failure rather than inferring it from the payload.
#[tauri::command]
async fn agent_query_stream(
    app: AppHandle,
    project_path: String,
    query: String,
    thread_id: Option<String>,
    stream_id: String,
) -> Result<(), String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    let url = agent_url(&metadata, "/v1/query/stream")?;
    let authorization = format!("Bearer {}", metadata.token);
    let mut body = json!({ "query": query });
    if let Some(thread_id) = thread_id {
        body["thread_id"] = json!(thread_id);
    }

    // Blocking IO on a worker thread: the response is consumed incrementally,
    // so awaiting it on the async runtime would occupy a reactor thread for the
    // whole run.
    tauri::async_runtime::spawn_blocking(move || {
        let response = ureq::post(&url)
            .set("Authorization", &authorization)
            .set("Accept", "text/event-stream")
            .timeout(Duration::from_secs(600))
            .send_json(body);
        let response = match response {
            Ok(response) => response,
            Err(error) => {
                emit_stream(&app, &stream_id, "error", &error.to_string());
                return;
            }
        };
        let reader = BufReader::new(response.into_reader());
        let mut event = String::new();
        let mut data: Vec<String> = Vec::new();
        for line in reader.lines() {
            let Ok(line) = line else {
                emit_stream(&app, &stream_id, "error", "the agent stream was interrupted");
                return;
            };
            if line.is_empty() {
                if !data.is_empty() {
                    emit_stream(&app, &stream_id, &event, &data.join("\n"));
                }
                event.clear();
                data.clear();
                continue;
            }
            if let Some(rest) = line.strip_prefix("event:") {
                event = rest.trim().to_string();
            } else if let Some(rest) = line.strip_prefix("data:") {
                data.push(rest.strip_prefix(' ').unwrap_or(rest).to_string());
            }
        }
        if !data.is_empty() {
            emit_stream(&app, &stream_id, &event, &data.join("\n"));
        }
    })
    .await
    .map_err(|error| format!("agent stream task failed: {error}"))
}

fn emit_stream(app: &AppHandle, stream_id: &str, event: &str, data: &str) {
    let _ = app.emit(
        "agent://stream",
        json!({ "streamId": stream_id, "event": event, "data": data }),
    );
}

/// Who this machine records as the approver.
#[tauri::command]
fn agent_operator_settings(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/settings/operator",
        None,
        Duration::from_secs(15),
    )
}

/// Records the approver's name. The Agent mints and keeps the id.
#[tauri::command]
fn agent_save_operator_settings(project_path: String, name: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/settings/operator",
        Some(json!({ "name": name })),
        Duration::from_secs(30),
    )
}

/// The user-supplied endpoint, without its credential.
#[tauri::command]
fn agent_provider_settings(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/settings/provider",
        None,
        Duration::from_secs(15),
    )
}

/// Records the endpoint. An empty key keeps the stored one.
///
/// The credential passes through this process to the Agent and is not held
/// here: the Workbench has never been the place that keeps it, and the user
/// store is now the one place on disk that does.
#[tauri::command]
fn agent_save_provider_settings(
    project_path: String,
    base_url: String,
    api_key: String,
    model: String,
) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/settings/provider",
        Some(json!({ "base_url": base_url, "api_key": api_key, "model": model })),
        Duration::from_secs(30),
    )
}

/// Clears the stored endpoint and credential.
#[tauri::command]
fn agent_forget_provider_settings(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/settings/provider/forget",
        Some(json!({})),
        Duration::from_secs(30),
    )
}

/// State integrity and tool availability.
#[tauri::command]
fn agent_project_health(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/project/health",
        None,
        Duration::from_secs(30),
    )
}

/// The committed event log, newest first.
#[tauri::command]
fn agent_project_history(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/project/history",
        None,
        Duration::from_secs(30),
    )
}

/// Rebuilds the derived state snapshot. `apply` false previews the work.
#[tauri::command]
fn agent_project_reconcile(project_path: String, apply: bool) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/project/reconcile",
        Some(json!({ "apply": apply })),
        Duration::from_secs(60),
    )
}

/// What a prototype decision needs, and whether it can be made yet.
#[tauri::command]
fn agent_decision(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/decision",
        None,
        Duration::from_secs(15),
    )
}

/// Records the prototype decision. This is what moves the stage out of
/// PROTOTYPE_DECISION; the core refuses a plain advance from there.
#[tauri::command]
fn agent_decide(
    project_path: String,
    decision: String,
    evidence_ids: Vec<String>,
    rationale: String,
    revised_fields: Option<Value>,
) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    let mut body = json!({
        "decision": decision,
        "evidence_ids": evidence_ids,
        "rationale": rationale,
    });
    if let Some(fields) = revised_fields {
        body["revised_fields"] = fields;
    }
    agent_request(
        &metadata,
        "POST",
        "/v1/decision",
        Some(body),
        Duration::from_secs(30),
    )
}

/// Whether the stage allows playtest work, and whether a protocol exists.
#[tauri::command]
fn agent_playtest(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/playtest",
        None,
        Duration::from_secs(15),
    )
}

/// Asks the model for a playtest protocol. Records nothing.
#[tauri::command]
fn agent_playtest_draft(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    // A model round trip, so this outlasts the Agent's own request timeout.
    agent_request(
        &metadata,
        "POST",
        "/v1/playtest/protocol/draft",
        Some(json!({})),
        Duration::from_secs(180),
    )
}

/// Records a reviewed playtest protocol.
#[tauri::command]
fn agent_playtest_protocol(project_path: String, content: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/playtest/protocol",
        Some(json!({ "content": content })),
        Duration::from_secs(30),
    )
}

/// Imports an observed playtest report.
#[tauri::command]
fn agent_playtest_report(project_path: String, report: Value) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/playtest/report",
        Some(json!({ "report": report })),
        Duration::from_secs(30),
    )
}

/// Picks a screenshot to register as visual evidence.
///
/// A native dialog rather than a typed path: the Workbench should not invent a
/// filesystem entry point, and what the user picked is what gets checksummed.
#[tauri::command]
async fn select_capture_file(app: AppHandle) -> Result<Option<String>, String> {
    let Some(selection) = app
        .dialog()
        .file()
        .set_title("Register a screenshot")
        .add_filter("Images", &["png", "jpg", "jpeg", "webp"])
        .blocking_pick_file()
    else {
        return Ok(None);
    };
    let selected = selection
        .into_path()
        .map_err(|error| format!("selected capture is not a local file: {error}"))?;
    if !selected.is_file() {
        return Err("selected capture is not a file".to_string());
    }
    selected
        .to_str()
        .map(|path| Some(path.to_string()))
        .ok_or_else(|| "selected capture path is not valid UTF-8".to_string())
}

/// Registers a screenshot as visual evidence. Captures nothing itself.
#[tauri::command]
fn agent_capture(project_path: String, path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/capture",
        Some(json!({ "path": path })),
        Duration::from_secs(30),
    )
}

/// Registered evidence, newest first.
#[tauri::command]
fn agent_evidence(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/evidence",
        None,
        Duration::from_secs(15),
    )
}

/// Whether a stage transition is allowed, and what is blocking it.
///
/// Sent as a POST once arguments are involved. The early decision gate tests
/// the reason and approver it is given rather than anything recorded, so
/// checking without them would report requirements the advance would satisfy.
#[tauri::command]
fn agent_gate(
    project_path: String,
    stage: String,
    reason: Option<String>,
    rationale: Option<String>,
) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    let parameterless = reason.is_none() && rationale.is_none();
    if parameterless {
        // The stage is a path segment here, so it is constrained rather than
        // trusted: only the core's own uppercase stage names can be formed.
        if stage.is_empty() || !stage.bytes().all(|b| b.is_ascii_uppercase() || b == b'_') {
            return Err("Stage must be an uppercase stage name".to_string());
        }
        return agent_request(
            &metadata,
            "GET",
            &format!("/v1/gate/{stage}"),
            None,
            Duration::from_secs(15),
        );
    }
    let mut body = json!({ "stage": stage });
    if let Some(value) = reason {
        body["reason"] = json!(value);
    }
    if let Some(why) = rationale {
        body["rationale"] = json!(why);
    }
    agent_request(
        &metadata,
        "POST",
        "/v1/gate",
        Some(body),
        Duration::from_secs(15),
    )
}

/// Performs a stage transition. The core refuses a blocked gate.
#[tauri::command]
fn agent_advance(
    project_path: String,
    stage: String,
    reason: Option<String>,
    rationale: Option<String>,
) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    let mut body = json!({ "stage": stage });
    if let Some(value) = reason {
        body["reason"] = json!(value);
    }
    if let Some(why) = rationale {
        body["rationale"] = json!(why);
    }
    agent_request(
        &metadata,
        "POST",
        "/v1/advance",
        Some(body),
        Duration::from_secs(30),
    )
}

/// The active hypothesis, or the absence of one.
#[tauri::command]
fn agent_hypothesis(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/hypothesis",
        None,
        Duration::from_secs(15),
    )
}

/// Asks the model for a hypothesis draft. Records nothing.
#[tauri::command]
fn agent_hypothesis_draft(project_path: String, brief: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    // A model round trip, so this outlasts the Agent's own request timeout.
    agent_request(
        &metadata,
        "POST",
        "/v1/hypothesis/draft",
        Some(json!({ "brief": brief })),
        Duration::from_secs(180),
    )
}

/// Records a hypothesis from reviewed fields.
///
/// Only the rationale is carried. The approver is resolved by the Agent from
/// the operator it stores, so no surface has to know who is at the machine.
#[tauri::command]
fn agent_hypothesis_create(
    project_path: String,
    fields: Value,
    rationale: Option<String>,
) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    let mut body = json!({ "fields": fields });
    if let Some(why) = rationale {
        body["rationale"] = json!(why);
    }
    agent_request(
        &metadata,
        "POST",
        "/v1/hypothesis",
        Some(body),
        Duration::from_secs(30),
    )
}

/// Creates Loopforge project state in this directory.
///
/// Idempotent in the core, so a repeated call adopts the existing project
/// rather than failing; the response says which happened.
#[tauri::command]
fn agent_project_init(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/project/init",
        None,
        Duration::from_secs(30),
    )
}

/// The project's lifecycle stage and derived quality claims.
#[tauri::command]
fn agent_project_status(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/project/status",
        None,
        Duration::from_secs(15),
    )
}

/// Engine run history. `operation` narrows to `build` or `test`.
#[tauri::command]
fn agent_runs(project_path: String, operation: Option<String>) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    // The path is built from a closed set rather than interpolated, so a
    // caller cannot reach an arbitrary Agent route through this parameter.
    let path = match operation.as_deref() {
        None => "/v1/runs",
        Some("build") => "/v1/runs?operation=build",
        Some("test") => "/v1/runs?operation=test",
        Some(other) => return Err(format!("unsupported run operation: {other}")),
    };
    agent_request(&metadata, "GET", path, None, Duration::from_secs(15))
}

/// One run, including its captured output.
#[tauri::command]
fn agent_run(project_path: String, run_id: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    if !run_id
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
        || run_id.is_empty()
    {
        return Err("invalid run id".to_string());
    }
    agent_request(
        &metadata,
        "GET",
        &format!("/v1/runs/{run_id}"),
        None,
        Duration::from_secs(15),
    )
}

/// Runs a build or test through the deterministic core.
#[tauri::command]
fn agent_run_engine(project_path: String, operation: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    // Engine runs compile a project; the Agent's own timeout is the real
    // bound, this one only has to outlast it.
    agent_request(
        &metadata,
        "POST",
        "/v1/engine/run",
        Some(json!({ "operation": operation })),
        Duration::from_secs(300),
    )
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
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            select_project_directory,
            agent_status,
            agent_start,
            agent_stop,
            agent_query,
            agent_providers,
            agent_sessions,
            agent_query_stream,
            agent_runs,
            agent_run,
            agent_run_engine,
            agent_project_init,
            agent_operator_settings,
            agent_save_operator_settings,
            agent_provider_settings,
            agent_save_provider_settings,
            agent_forget_provider_settings,
            agent_project_health,
            agent_project_history,
            agent_project_reconcile,
            agent_decision,
            agent_decide,
            agent_playtest,
            agent_playtest_draft,
            agent_playtest_protocol,
            agent_playtest_report,
            select_capture_file,
            agent_capture,
            agent_evidence,
            agent_gate,
            agent_advance,
            agent_hypothesis,
            agent_hypothesis_draft,
            agent_hypothesis_create,
            agent_project_status
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
