mod userstore;

use std::fs::{self, OpenOptions};
use std::io;
use std::io::{BufRead, BufReader};
use std::net::{SocketAddr, TcpListener};
use std::sync::{Mutex, OnceLock};
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
    /// The Agent process, so it can be ended with the window that opened it.
    ///
    /// Recorded rather than only held in memory: an app that crashed leaves an
    /// Agent behind, and the next launch has to be able to adopt or replace it
    /// instead of leaving a process the user never asked for running forever.
    #[serde(default)]
    pid: u32,
}

/// The `PATH` a terminal on this machine would have.
///
/// A desktop app launched from Finder inherits a minimal `PATH` -- typically
/// `/usr/bin:/bin:/usr/sbin:/sbin` -- and not the one the user's shell builds
/// from its profile. Everything the Agent shells out to is therefore invisible
/// to it: this was first noticed as Kura reporting "provider CLI is not
/// available" for a `claude` that was installed and signed in, at
/// `~/.local/bin/claude`, and it applies equally to the engine binaries and to
/// git.
///
/// Resolved once, by asking the login shell. Interactive as well as login,
/// because `PATH` is as often set in `.zshrc` as in `.zprofile`.
#[cfg(unix)]
fn login_shell_path() -> Option<String> {
    static RESOLVED: OnceLock<Option<String>> = OnceLock::new();
    RESOLVED
        .get_or_init(|| {
            let shell = std::env::var("SHELL").ok().filter(|value| !value.trim().is_empty())?;
            let output = Command::new(shell)
                .args(["-ilc", "printf %s \"$PATH\""])
                .stdin(Stdio::null())
                .output()
                .ok()?;
            let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
            (!path.is_empty()).then_some(path)
        })
        .clone()
}

/// The inherited `PATH` with anything the login shell knows about appended.
///
/// Appended rather than substituted: the inherited value can carry entries a
/// packaged app relies on, and dropping them to gain the user's would trade
/// one set of missing tools for another.
#[cfg(unix)]
fn enriched_path() -> String {
    let inherited = std::env::var("PATH").unwrap_or_default();
    let Some(from_shell) = login_shell_path() else {
        return inherited;
    };
    // Both sides are deduplicated. The inherited value routinely lists the
    // same directory twice on its own, and this string is handed to every
    // child process and searched on every lookup.
    let mut entries: Vec<&str> = Vec::new();
    for entry in inherited
        .split(':')
        .chain(from_shell.split(':'))
        .filter(|part| !part.is_empty())
    {
        if !entries.contains(&entry) {
            entries.push(entry);
        }
    }
    entries.join(":")
}

/// Agent processes this app is responsible for ending.
///
/// The lifetime of an Agent -- and of the runtime it supervises -- is the
/// lifetime of the app. A `Child` dropped at the end of a command does not end
/// its process, so without this the Agent outlived every window that ever
/// opened it, and a fix never reached the user because the stale process kept
/// answering.
static SUPERVISED: Mutex<Vec<u32>> = Mutex::new(Vec::new());

/// Matched against the process table when reclaiming orphans.
const AGENT_BINARY_NAME: &str = "loopforge-agent";

/// Whether this app run is the one that started that Agent.
fn supervised(pid: u32) -> bool {
    SUPERVISED.lock().map(|pids| pids.contains(&pid)).unwrap_or(false)
}

/// Ends every Agent serving this project that this run did not start.
///
/// Orphans are the app's problem, not the user's. An Agent left by a crashed
/// or force-quit launch keeps answering on its old port, so the shell talks to
/// a previous build, a rebuilt sidecar never reaches the user, and the only
/// recovery is finding and killing a process by hand -- which nobody outside
/// this repository is going to do.
///
/// The recorded address is used to ask politely and then discarded. It is
/// never waited on and never reused: the replacement gets a fresh port, so a
/// port that stays held by something else cannot block a working start.
async fn reclaim_agents(root: &Path) {
    if let Ok(Some(metadata)) = load_runtime(root) {
        // Politely first, because the Agent stops its Kura daemon on the way
        // out; killing it outright would leave that daemon running instead.
        let _ = agent_request(
            &metadata,
            "POST",
            "/v1/shutdown",
            Some(json!({})),
            Duration::from_secs(5),
        ).await;
        if metadata.pid > 0 && !supervised(metadata.pid) {
            terminate(metadata.pid);
        }
        let _ = fs::remove_file(runtime_path(root));
    }
    // And anything the metadata no longer knows about. A file deleted while an
    // Agent was running leaves a process nothing can name, which is exactly
    // the case a user cannot recover from.
    for pid in agent_pids_for(root) {
        if !supervised(pid) {
            terminate(pid);
        }
    }
}

/// Agent processes serving this project, by inspecting the process table.
#[cfg(unix)]
fn agent_pids_for(root: &Path) -> Vec<u32> {
    let Ok(output) = Command::new("ps").args(["-axo", "pid=,args="]).output() else {
        return Vec::new();
    };
    let needle = format!("--project {}", root.display());
    String::from_utf8_lossy(&output.stdout)
        .lines()
        .filter(|line| line.contains(AGENT_BINARY_NAME) && line.contains(&needle))
        .filter_map(|line| line.trim().split_whitespace().next()?.parse().ok())
        .collect()
}

#[cfg(not(unix))]
fn agent_pids_for(_root: &Path) -> Vec<u32> {
    Vec::new()
}

/// Ends one process, politely then not.
fn terminate(pid: u32) {
    #[cfg(unix)]
    {
        unsafe { libc::kill(pid as i32, libc::SIGTERM) };
        for _ in 0..30 {
            thread::sleep(Duration::from_millis(100));
            if unsafe { libc::kill(pid as i32, 0) } != 0 {
                return;
            }
        }
        unsafe { libc::kill(pid as i32, libc::SIGKILL) };
    }
    #[cfg(not(unix))]
    let _ = pid;
}

fn supervise(pid: u32) {
    if let Ok(mut pids) = SUPERVISED.lock() {
        if !pids.contains(&pid) {
            pids.push(pid);
        }
    }
}

/// Ends every supervised Agent, and with it the runtime each one started.
///
/// `SIGTERM` first and only then `SIGKILL`: the Agent stops its Kura daemon in
/// a signal handler, so killing it outright would orphan the very process this
/// is trying to clean up.
fn stop_supervised() {
    let pids = SUPERVISED.lock().map(|mut p| std::mem::take(&mut *p)).unwrap_or_default();
    #[cfg(unix)]
    for pid in &pids {
        unsafe { libc::kill(*pid as i32, libc::SIGTERM) };
    }
    if pids.is_empty() {
        return;
    }
    // Long enough for the Agent to stop its daemon, short enough that quitting
    // still feels immediate.
    for _ in 0..30 {
        thread::sleep(Duration::from_millis(100));
        #[cfg(unix)]
        if pids
            .iter()
            .all(|pid| unsafe { libc::kill(*pid as i32, 0) } != 0)
        {
            return;
        }
    }
    #[cfg(unix)]
    for pid in &pids {
        unsafe { libc::kill(*pid as i32, libc::SIGKILL) };
    }
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

/// One request to the Agent, off whichever thread asked for it.
///
/// The HTTP client is blocking and some of these wait a long time -- a browser
/// sign-in is allowed five minutes -- so the work is handed to a thread that
/// exists to be blocked. Run on the async runtime's workers instead, a single
/// sign-in would hold one for its whole duration and every other command would
/// queue behind it; run on the main thread, as these were, the window itself
/// stops responding.
async fn agent_request(
    metadata: &AgentRuntimeMetadata,
    method: &str,
    path: &str,
    body: Option<Value>,
    timeout: Duration,
) -> Result<Value, String> {
    let metadata = metadata.clone();
    let method = method.to_string();
    let path = path.to_string();
    tauri::async_runtime::spawn_blocking(move || {
        agent_request_blocking(&metadata, &method, &path, body, timeout)
    })
    .await
    .map_err(|error| format!("Loopforge Agent request did not finish: {error}"))?
}

fn agent_request_blocking(
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
        .map_err(|error| describe_agent_failure(error))?
        .into_json()
        .map_err(|error| format!("Loopforge Agent returned invalid JSON: {error}"))
}

/// What the Agent said, not merely that it refused.
///
/// `ureq` renders a failed status as "status code 400" and leaves the body
/// unread. The Agent answers every refusal with a message naming the cause --
/// which port is held, which account is not signed in, what the vendor
/// replied -- and dropping it left the user with a number and nowhere to go.
fn describe_agent_failure(error: ureq::Error) -> String {
    let ureq::Error::Status(status, response) = error else {
        return format!("Loopforge Agent request failed: {error}");
    };
    let body = response.into_string().unwrap_or_default();
    let detail = serde_json::from_str::<Value>(&body)
        .ok()
        .and_then(|value| {
            value
                .get("error")
                .and_then(|error| error.get("message"))
                .or_else(|| value.get("message"))
                .and_then(Value::as_str)
                .map(str::to_string)
        })
        // A body that is not the Agent's own shape is still better than
        // nothing, bounded so a stray HTML page cannot fill the surface.
        .unwrap_or_else(|| body.chars().take(300).collect());
    if detail.trim().is_empty() {
        format!("Loopforge Agent refused the request ({status})")
    } else {
        detail
    }
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

async fn agent_status_for_root(root: &Path) -> Result<Value, String> {
    let Some(metadata) = load_runtime(root)? else {
        return Ok(json!({
            "schema_version": "loopforge-agent-status-v1",
            "ready": false,
            "managed": false
        }));
    };
    match agent_request(&metadata, "GET", "/v1/status", None, Duration::from_secs(2)).await {
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
async fn agent_status(project_path: String) -> Result<Value, String> {
    agent_status_for_root(&project_root(&project_path)?).await
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
async fn agent_start(app: AppHandle, project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    // An Agent this run started is reused; anything else is reclaimed.
    //
    // An Agent left by a previous launch runs a previous build, and nothing
    // from the outside can tell which. Reusing it meant a rebuilt sidecar
    // never reached the user: the old process kept answering, kept failing the
    // same way, and restarting the app changed nothing.
    if let Some(metadata) = load_runtime(&root)? {
        if metadata.pid > 0 && supervised(metadata.pid) {
            let current = agent_status_for_root(&root).await?;
            if current.get("ready").and_then(Value::as_bool) == Some(true) {
                return Ok(current);
            }
            // Ours, but its runtime is down, which it can be asked to fix.
            if agent_request(&metadata, "GET", "/healthz", None, Duration::from_secs(2)).await.is_ok() {
                let mut status = agent_request(
                    &metadata,
                    "POST",
                    "/v1/start",
                    Some(json!({})),
                    Duration::from_secs(60),
                ).await?;
                if let Some(object) = status.as_object_mut() {
                    object.insert("managed".to_string(), Value::Bool(true));
                }
                return Ok(status);
            }
        }
    }
    reclaim_agents(&root).await;
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
    let mut metadata = AgentRuntimeMetadata {
        schema_version: AGENT_RUNTIME_SCHEMA.to_string(),
        bind_addr: format!("127.0.0.1:{port}"),
        token: format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple()),
        project_root: root.to_string_lossy().into_owned(),
        // Filled in once the process exists.
        pid: 0,
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
        // So the Agent, and the Kura daemon it starts, can find the tools a
        // terminal on this machine would find.
        .env("PATH", enriched_path())
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .spawn()
        .map_err(|error| format!("failed to start Loopforge Agent: {error}"))?;
    metadata.pid = child.id();
    supervise(metadata.pid);
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
        ).await
        .is_ok()
        {
            let mut status = agent_request(
                &metadata,
                "POST",
                "/v1/start",
                Some(json!({})),
                Duration::from_secs(15),
            ).await?;
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
    // Why it exited, before anything else. A sidecar killed by the operating
    // system -- an invalid code signature is the one that actually happens --
    // writes nothing at all, so reporting only the log leaves the user with an
    // error that names no cause.
    let exited = child.try_wait().ok().flatten();
    let _ = child.kill();
    let _ = fs::remove_file(runtime_path(&root));
    let log_tail = fs::read(&path).unwrap_or_default();
    let detail = command_error(&log_tail);
    let how = match exited {
        Some(status) => {
            #[cfg(unix)]
            {
                use std::os::unix::process::ExitStatusExt;
                match status.signal() {
                    Some(9) => " (killed by the system on launch: the sidecar's \
code signature was rejected; rebuild with pnpm build:agent)"
                        .to_string(),
                    Some(signal) => format!(" (killed by signal {signal})"),
                    None => format!(" (exited with status {})", status.code().unwrap_or(-1)),
                }
            }
            #[cfg(not(unix))]
            {
                format!(" (exited with status {})", status.code().unwrap_or(-1))
            }
        }
        None => String::new(),
    };
    Err(format!(
        "Loopforge Agent did not become ready{how}{}",
        if detail.is_empty() {
            String::new()
        } else {
            format!(": {detail}")
        }
    ))
}

#[tauri::command]
async fn agent_stop(project_path: String) -> Result<Value, String> {
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
    ).await?;
    fs::remove_file(runtime_path(&root))
        .map_err(|error| format!("Agent stopped but runtime metadata remains: {error}"))?;
    Ok(result)
}

/// Opens a URL in the user's own browser.
///
/// Restricted to `http` and `https`. The argument reaches the platform opener,
/// which will happily act on `file:` or a registered custom scheme, so the
/// scheme is checked here rather than trusted: the only thing this exists to
/// open is a vendor's sign-in page.
#[tauri::command]
async fn open_external(url: String) -> Result<(), String> {
    let parsed = Url::parse(url.trim()).map_err(|error| error.to_string())?;
    if !matches!(parsed.scheme(), "http" | "https") {
        return Err(format!("Refusing to open a {} URL", parsed.scheme()));
    }
    let program = if cfg!(target_os = "macos") {
        "open"
    } else if cfg!(target_os = "windows") {
        "explorer"
    } else {
        "xdg-open"
    };
    Command::new(program)
        .arg(parsed.as_str())
        .spawn()
        .map(|_| ())
        .map_err(|error| format!("Could not open a browser: {error}"))
}

/// Lists the subscription accounts that can be signed into.
#[tauri::command]
async fn agent_oauth_accounts(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/oauth/accounts",
        None,
        Duration::from_secs(15),
    ).await
}

/// Opens a sign-in, returning what the user has to act on: a URL to visit, or
/// a short code to type on the vendor's own page.
#[tauri::command]
async fn agent_oauth_begin(project_path: String, provider_id: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/oauth/begin",
        Some(json!({ "provider_id": provider_id })),
        Duration::from_secs(30),
    ).await
}

/// Waits for a sign-in to be completed in the browser.
///
/// The long timeout is the point: this call is the wait. It has to outlast a
/// user finding the right account, typing a password and clearing a second
/// factor, and a shell-side timeout firing first would abandon a sign-in that
/// was about to succeed.
#[tauri::command]
async fn agent_oauth_complete(project_path: String, provider_id: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/oauth/complete",
        Some(json!({ "provider_id": provider_id, "timeout": 300.0 })),
        Duration::from_secs(330),
    ).await
}

/// Forgets a stored grant. Local only; nothing is revoked at the vendor.
#[tauri::command]
async fn agent_oauth_sign_out(project_path: String, provider_id: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/oauth/sign-out",
        Some(json!({ "provider_id": provider_id })),
        Duration::from_secs(15),
    ).await
}

/// Reads how much of each subscription account has been used.
///
/// The figures come from what the borrowed CLIs wrote to disk, not from the
/// vendor: Loopforge holds no credential for a subscription. Each carries the
/// moment it was recorded so the surface can say how old it is.
#[tauri::command]
async fn agent_account_usage(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/account-usage",
        None,
        Duration::from_secs(15),
    ).await
}

/// Reads the generic provider inventory the Agent projects from Kura. Model
/// routing and credentials are runtime capabilities, so this is read-only and
/// the Workbench never reaches Kura directly.
#[tauri::command]
async fn agent_providers(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/providers",
        None,
        Duration::from_secs(15),
    ).await
}

/// Reads the Agent's projection of the runtime's chat sessions.
#[tauri::command]
async fn agent_sessions(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/sessions",
        None,
        Duration::from_secs(15),
    ).await
}

/// Reads one conversation, so it can be reopened.
///
/// The listing carries a title and a count; the messages are fetched only when
/// a session is actually opened, because a project accumulates them and the
/// sidebar needs none of the text to draw a row.
#[tauri::command]
async fn agent_session(project_path: String, session_id: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    // Percent-encoded: the id reaches this from a listing rather than from a
    // user, but it lands in a request path either way.
    let encoded: String = url::form_urlencoded::byte_serialize(session_id.as_bytes()).collect();
    agent_request(
        &metadata,
        "GET",
        &format!("/v1/sessions/{encoded}"),
        None,
        Duration::from_secs(15),
    ).await
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

/// Recent projects, most recent first.
///
/// Read from the user store directly rather than through the Agent: this list
/// is needed on the first render to decide which project to reopen, and an
/// Agent is started per project, so asking one for the list of projects is
/// circular.
#[tauri::command]
async fn recent_projects() -> Vec<userstore::RecentProject> {
    userstore::recent_projects(50)
}

/// Records that a project was opened.
#[tauri::command]
async fn remember_project(project_path: String, mode: String) -> bool {
    let Ok(root) = project_root(&project_path) else {
        return false;
    };
    userstore::remember_project(&root.to_string_lossy(), &mode)
}

/// Removes a project from the recent list. The project itself is untouched.
#[tauri::command]
async fn forget_project(project_path: String) -> bool {
    userstore::forget_project(&project_path)
}

/// Who this machine records as the approver.
#[tauri::command]
async fn agent_operator_settings(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/settings/operator",
        None,
        Duration::from_secs(15),
    ).await
}

/// Records the approver's name. The Agent mints and keeps the id.
#[tauri::command]
async fn agent_save_operator_settings(project_path: String, name: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/settings/operator",
        Some(json!({ "name": name })),
        Duration::from_secs(30),
    ).await
}

/// The user-supplied endpoint, without its credential.
#[tauri::command]
async fn agent_provider_settings(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/settings/provider",
        None,
        Duration::from_secs(15),
    ).await
}

/// Records the endpoint. An empty key keeps the stored one.
///
/// The credential passes through this process to the Agent and is not held
/// here: the Workbench has never been the place that keeps it, and the user
/// store is now the one place on disk that does.
#[tauri::command]
async fn agent_save_provider_settings(
    project_path: String,
    base_url: String,
    api_key: String,
    model: String,
    display_name: String,
    protocol: String,
    oauth_provider_id: String,
    provider_id: String,
) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/settings/provider",
        Some(json!({
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
            "display_name": display_name,
            "protocol": protocol,
            "oauth_provider_id": oauth_provider_id,
            "provider_id": provider_id,
        })),
        Duration::from_secs(30),
    ).await
}

/// Asks an endpoint for its model list, before anything is stored.
#[tauri::command]
async fn agent_probe_provider(
    project_path: String,
    base_url: String,
    api_key: String,
    protocol: String,
    oauth_provider_id: String,
) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    // Longer than a local call: this reaches a vendor over the network.
    //
    // Every parameter is forwarded. `protocol` and `oauth_provider_id` were
    // accepted here and then left out of the body, so the Agent fell back to
    // its defaults: it asked every endpoint for `/models` in the OpenAI shape
    // with no credential. Against Anthropic that is a 404, which the wizard
    // reported as "this endpoint published no model list" -- on the step whose
    // entire purpose is that list, for a vendor that does publish one.
    agent_request(
        &metadata,
        "POST",
        "/v1/settings/provider/probe",
        Some(json!({
            "base_url": base_url,
            "api_key": api_key,
            "protocol": protocol,
            "oauth_provider_id": oauth_provider_id,
        })),
        Duration::from_secs(45),
    ).await
}


/// Moves a managed provider's sign-in along. Nothing is spawned here: the

/// Points one modality at a provider. Routing lives in Kura.
#[tauri::command]
async fn agent_route_role(
    project_path: String,
    role: String,
    provider_id: String,
    model: String,
) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/settings/role",
        Some(json!({ "role": role, "provider_id": provider_id, "model": model })),
        Duration::from_secs(30),
    ).await
}

/// Leaves a modality unrouted.
#[tauri::command]
async fn agent_clear_role(project_path: String, role: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/settings/role/clear",
        Some(json!({ "role": role })),
        Duration::from_secs(30),
    ).await
}

/// Removes one provider: its stored endpoint, its credential, and its
/// registration in the running runtime.
#[tauri::command]
async fn agent_forget_provider_settings(
    project_path: String,
    provider_id: String,
) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/settings/provider/forget",
        Some(json!({ "provider_id": provider_id })),
        Duration::from_secs(30),
    ).await
}

/// State integrity and tool availability.
#[tauri::command]
async fn agent_project_health(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/project/health",
        None,
        Duration::from_secs(30),
    ).await
}

/// Directories whose contents are not the project.
///
/// Mirrors the core's `GENERATED_DIRS`, plus the dependency trees a person
/// never means when they type `@`. Listing them would bury the handful of files
/// someone is looking for under thousands they are not.
const NOT_THE_PROJECT: &[&str] = &[
    ".loopforge",
    ".git",
    ".godot",
    "build",
    "dist",
    "artifacts",
    "captures",
    "node_modules",
    "target",
    ".venv",
    "__pycache__",
];

/// How many paths a completion menu is given.
///
/// A menu is read, not scrolled through: past a screenful the answer is to type
/// more of the name. The cap also bounds the walk, so opening `@` in a large
/// repository does not stall the window.
const MAX_PROJECT_FILES: usize = 500;

/// Files in the project, for completing an `@` mention.
///
/// Walked here rather than asked of the Agent: this answers on a keystroke, and
/// a round trip through the Agent and back would be felt on every character.
#[tauri::command]
async fn project_files(project_path: String, query: String) -> Result<Vec<String>, String> {
    let root = project_root(&project_path)?;
    let needle = query.trim().to_lowercase();
    let mut found: Vec<String> = Vec::new();
    let mut pending = vec![root.clone()];

    while let Some(directory) = pending.pop() {
        if found.len() >= MAX_PROJECT_FILES {
            break;
        }
        let Ok(entries) = std::fs::read_dir(&directory) else {
            // A directory that cannot be read is skipped rather than failing
            // the listing: one unreadable folder must not hide the rest.
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let Some(name) = path.file_name().and_then(|name| name.to_str()) else {
                continue;
            };
            // `file_type` rather than `is_dir`, so a symlink is not followed:
            // one pointing outside the project would list files that are not
            // in it, and one pointing at an ancestor would never terminate.
            let Ok(kind) = entry.file_type() else { continue };
            if kind.is_symlink() {
                continue;
            }
            if kind.is_dir() {
                if !NOT_THE_PROJECT.contains(&name) && !name.starts_with('.') {
                    pending.push(path);
                }
                continue;
            }
            let Ok(relative) = path.strip_prefix(&root) else { continue };
            let Some(relative) = relative.to_str() else { continue };
            if needle.is_empty() || relative.to_lowercase().contains(&needle) {
                found.push(relative.to_string());
                if found.len() >= MAX_PROJECT_FILES {
                    break;
                }
            }
        }
    }

    // Shortest first: a person typing `@main` wants `main.gd`, not
    // `scenes/levels/main_menu_background.tscn`.
    found.sort_by(|a, b| a.len().cmp(&b.len()).then_with(|| a.cmp(b)));
    Ok(found)
}

/// Tool calls waiting on a person.
///
/// Polled while a turn is running: the Agent holds the call open while it waits,
/// so a surface that only looked once would show nothing and the turn would time
/// out with the question never asked.
#[tauri::command]
async fn agent_approvals(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(&metadata, "GET", "/v1/approvals", None, Duration::from_secs(15)).await
}

/// Answer one. The waiting call continues or stops immediately.
#[tauri::command]
async fn agent_resolve_approval(
    project_path: String,
    approval_id: String,
    approved: bool,
    comment: String,
) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/approvals/resolve",
        Some(json!({
            "approval_id": approval_id,
            "approved": approved,
            "comment": comment,
        })),
        Duration::from_secs(30),
    ).await
}

/// How much the agent may do without asking, and what the modes mean.
#[tauri::command]
async fn agent_permissions(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(&metadata, "GET", "/v1/permissions", None, Duration::from_secs(15)).await
}

/// Change it. Takes effect on the next tool call.
#[tauri::command]
async fn agent_save_permissions(project_path: String, mode: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/permissions",
        Some(json!({ "mode": mode })),
        Duration::from_secs(30),
    ).await
}

/// The committed event log, newest first.
#[tauri::command]
async fn agent_project_history(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/project/history",
        None,
        Duration::from_secs(30),
    ).await
}

/// Rebuilds the derived state snapshot. `apply` false previews the work.
#[tauri::command]
async fn agent_project_reconcile(project_path: String, apply: bool) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/project/reconcile",
        Some(json!({ "apply": apply })),
        Duration::from_secs(60),
    ).await
}

/// What a prototype decision needs, and whether it can be made yet.
#[tauri::command]
async fn agent_decision(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/decision",
        None,
        Duration::from_secs(15),
    ).await
}

/// Records the prototype decision. This is what moves the stage out of
/// PROTOTYPE_DECISION; the core refuses a plain advance from there.
#[tauri::command]
async fn agent_decide(
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
    ).await
}

/// Whether the stage allows playtest work, and whether a protocol exists.
#[tauri::command]
async fn agent_playtest(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/playtest",
        None,
        Duration::from_secs(15),
    ).await
}

/// Asks the model for a playtest protocol. Records nothing.
#[tauri::command]
async fn agent_playtest_draft(project_path: String) -> Result<Value, String> {
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
    ).await
}

/// Records a reviewed playtest protocol.
#[tauri::command]
async fn agent_playtest_protocol(project_path: String, content: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/playtest/protocol",
        Some(json!({ "content": content })),
        Duration::from_secs(30),
    ).await
}

/// Imports an observed playtest report.
#[tauri::command]
async fn agent_playtest_report(project_path: String, report: Value) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/playtest/report",
        Some(json!({ "report": report })),
        Duration::from_secs(30),
    ).await
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
async fn agent_capture(project_path: String, path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/capture",
        Some(json!({ "path": path })),
        Duration::from_secs(30),
    ).await
}

/// Registered evidence, newest first.
#[tauri::command]
async fn agent_evidence(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/evidence",
        None,
        Duration::from_secs(15),
    ).await
}

/// Whether a stage transition is allowed, and what is blocking it.
///
/// Sent as a POST once arguments are involved. The early decision gate tests
/// the reason and approver it is given rather than anything recorded, so
/// checking without them would report requirements the advance would satisfy.
#[tauri::command]
async fn agent_gate(
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
        ).await;
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
    ).await
}

/// Performs a stage transition. The core refuses a blocked gate.
#[tauri::command]
async fn agent_advance(
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
    ).await
}

/// The active hypothesis, or the absence of one.
#[tauri::command]
async fn agent_hypothesis(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/hypothesis",
        None,
        Duration::from_secs(15),
    ).await
}

/// Asks the model for a hypothesis draft. Records nothing.
#[tauri::command]
async fn agent_hypothesis_draft(project_path: String, brief: String) -> Result<Value, String> {
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
    ).await
}

/// Records a hypothesis from reviewed fields.
///
/// Only the rationale is carried. The approver is resolved by the Agent from
/// the operator it stores, so no surface has to know who is at the machine.
#[tauri::command]
async fn agent_hypothesis_create(
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
    ).await
}

/// Creates Loopforge project state in this directory.
///
/// Idempotent in the core, so a repeated call adopts the existing project
/// rather than failing; the response says which happened.
#[tauri::command]
async fn agent_project_init(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "POST",
        "/v1/project/init",
        None,
        Duration::from_secs(30),
    ).await
}

/// The project's lifecycle stage and derived quality claims.
#[tauri::command]
async fn agent_project_status(project_path: String) -> Result<Value, String> {
    let root = project_root(&project_path)?;
    let metadata = load_runtime(&root)?
        .ok_or_else(|| "Loopforge Agent has not been started for this project".to_string())?;
    agent_request(
        &metadata,
        "GET",
        "/v1/project/status",
        None,
        Duration::from_secs(15),
    ).await
}

/// Engine run history. `operation` narrows to `build` or `test`.
#[tauri::command]
async fn agent_runs(project_path: String, operation: Option<String>) -> Result<Value, String> {
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
    agent_request(&metadata, "GET", path, None, Duration::from_secs(15)).await
}

/// One run, including its captured output.
#[tauri::command]
async fn agent_run(project_path: String, run_id: String) -> Result<Value, String> {
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
    ).await
}

/// Runs a build or test through the deterministic core.
#[tauri::command]
async fn agent_run_engine(project_path: String, operation: String) -> Result<Value, String> {
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
    ).await
}

#[tauri::command]
async fn agent_query(
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
    ).await
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
            agent_account_usage,
            agent_oauth_accounts,
            open_external,
            agent_oauth_begin,
            agent_oauth_complete,
            agent_oauth_sign_out,
            agent_sessions,
            agent_session,
            agent_query_stream,
            agent_runs,
            agent_run,
            agent_run_engine,
            agent_project_init,
            recent_projects,
            remember_project,
            forget_project,
            agent_operator_settings,
            agent_save_operator_settings,
            agent_provider_settings,
            agent_probe_provider,
            agent_route_role,
            agent_clear_role,
            agent_save_provider_settings,
            agent_forget_provider_settings,
            agent_project_health,
            project_files,
            agent_approvals,
            agent_resolve_approval,
            agent_permissions,
            agent_save_permissions,
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
        .build(tauri::generate_context!())
        .expect("error while running Loopforge Workbench")
        .run(|_app, event| {
            // The Agent -- and the Kura daemon it supervises -- live exactly as
            // long as the app. Both `Exit` and `ExitRequested` are handled
            // because a window closed by the user reaches one and a quit
            // reaches the other, and an Agent that survives either is a process
            // the user never asked to keep running.
            if matches!(
                event,
                tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }
            ) {
                stop_supervised();
            }
        });
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
            pid: 0,
        }
    }

    /// A process that looks like an Agent for `root`, without being one.
    fn fake_agent(root: &Path) -> std::process::Child {
        Command::new("/bin/sh")
            .args([
                "-c",
                &format!(
                    "exec -a '{} serve --project {} --host 127.0.0.1' sleep 30",
                    AGENT_BINARY_NAME,
                    root.display()
                ),
            ])
            .spawn()
            .expect("spawned")
    }

    #[test]
    fn no_command_blocks_the_thread_that_draws_the_window() {
        // Tauri runs a synchronous command on the main thread. These wait on a
        // blocking HTTP client -- a browser sign-in is allowed five minutes,
        // an engine run ten -- so one synchronous command freezes the window
        // for as long as it waits. That is what a completed sign-in did.
        //
        // Read from this file rather than asserted on behaviour: the property
        // is that every command is declared `async`, and a test that called
        // one could only ever cover the one it called.
        let source = include_str!("lib.rs");
        // Assembled rather than written out, or this line is itself a match.
        let marker = concat!("#[tauri::", "command]");
        let offenders: Vec<&str> = source
            .split(marker)
            .skip(1)
            .filter_map(|block| {
                let declaration = block.trim_start().lines().next()?;
                (!declaration.starts_with("async fn")).then_some(declaration)
            })
            .collect();

        assert!(offenders.is_empty(), "synchronous commands: {offenders:?}");
    }

    #[test]
    fn every_command_uses_every_argument_it_accepts() {
        // A command that takes a parameter and never mentions it again is a
        // silent data loss: the front end sends a value, the signature accepts
        // it, and the Agent is handed a request without it and falls back to a
        // default.
        //
        // `agent_probe_provider` did exactly this with `protocol` and
        // `oauth_provider_id`. Every endpoint was asked for `/models` in the
        // OpenAI shape with no credential, so a subscription vendor answered
        // 404 and the wizard reported that it published no models. Nothing on
        // either side could see it: the front-end tests mock the boundary this
        // sits behind, and the Agent tests call the Agent directly.
        //
        // Read from this file for the same reason the test above is: the
        // property holds over every command, and calling one covers one.
        let source = include_str!("lib.rs");
        let marker = concat!("#[tauri::", "command]");
        let mut offenders: Vec<String> = Vec::new();
        for block in source.split(marker).skip(1) {
            let Some((signature, rest)) = block.split_once(") -> ") else { continue };
            let Some((name, arguments)) = signature.split_once('(') else { continue };
            let name = name.trim().trim_start_matches("async fn").trim();
            // The body only: a parameter naming itself in its own declaration
            // is not a use of it.
            let Some(body) = rest.split_once('{').map(|(_, body)| body) else { continue };
            let body = match body.find("\n}\n") {
                Some(end) => &body[..end],
                None => body,
            };
            // Comments do not use anything. Matching against them is how the
            // first version of this test passed on the very defect it was
            // written for: the comment explaining the fix named both dropped
            // parameters, which was enough to satisfy the search.
            let body: String = body
                .lines()
                .map(|line| line.split("//").next().unwrap_or(""))
                .collect::<Vec<_>>()
                .join("\n");
            for argument in arguments.split(',') {
                let Some((parameter, _)) = argument.split_once(':') else { continue };
                let parameter = parameter.trim();
                if parameter.is_empty() || parameter.starts_with('#') || parameter == "app" {
                    continue;
                }
                // Word-boundary match, so `api_key` is not satisfied by
                // `api_key_env` and `protocol` not by `protocols`.
                let used = body.match_indices(parameter).any(|(at, _)| {
                    let before = body[..at].chars().next_back();
                    let after = body[at + parameter.len()..].chars().next();
                    let boundary = |c: Option<char>| {
                        !matches!(c, Some(c) if c.is_alphanumeric() || c == '_')
                    };
                    boundary(before) && boundary(after)
                });
                if !used {
                    offenders.push(format!("{name}({parameter})"));
                }
            }
        }

        assert!(offenders.is_empty(), "arguments accepted and dropped: {offenders:?}");
    }

    #[test]
    fn the_shell_path_reaches_tools_a_terminal_would_find() {
        // A desktop app launched from Finder gets a minimal PATH, so a CLI the
        // user installed under their home directory is invisible to it. That
        // is what made Kura report an installed, signed-in `claude` as
        // unavailable.
        let enriched = enriched_path();
        let inherited = std::env::var("PATH").unwrap_or_default();

        for entry in inherited.split(':').filter(|part| !part.is_empty()) {
            assert!(enriched.split(':').any(|part| part == entry), "dropped {entry}");
        }
        if let Some(from_shell) = login_shell_path() {
            for entry in from_shell.split(':').filter(|part| !part.is_empty()) {
                assert!(enriched.split(':').any(|part| part == entry), "missing {entry}");
            }
        }
    }

    #[test]
    fn the_path_carries_no_duplicates() {
        // It is passed to every child process and read on every lookup; the
        // same directory appearing twice is a lookup cost for nothing.
        let enriched = enriched_path();
        let mut seen = std::collections::HashSet::new();

        for entry in enriched.split(':').filter(|part| !part.is_empty()) {
            assert!(seen.insert(entry), "duplicate {entry}");
        }
    }

    #[test]
    fn an_orphan_is_found_by_the_project_it_serves() {
        // The case a user cannot recover from: an Agent still running with no
        // metadata naming it. It has to be findable from the process table, or
        // it stays up forever answering for a build nobody is running.
        let root = temporary_root("orphan-scan");
        let child = fake_agent(&root);
        let pid = child.id();
        thread::sleep(Duration::from_millis(400));

        let found = agent_pids_for(&root);
        terminate(pid);

        assert!(found.contains(&pid), "expected {pid} in {found:?}");
    }

    #[test]
    fn an_agent_serving_another_project_is_left_alone() {
        // Reclaiming is scoped to the project being opened. A sweep that also
        // took a sibling project's Agent would make opening one window close
        // another's.
        let mine = temporary_root("scan-mine");
        let theirs = temporary_root("scan-theirs");
        let child = fake_agent(&theirs);
        let pid = child.id();
        thread::sleep(Duration::from_millis(400));

        let found = agent_pids_for(&mine);
        terminate(pid);

        assert!(!found.contains(&pid), "swept another project's Agent");
    }

    #[test]
    fn a_recorded_agent_survives_a_round_trip_so_a_later_launch_can_end_it() {
        // The whole point of writing the pid down: an app that crashed leaves
        // an Agent behind, and the next launch has to be able to find it.
        let root = temporary_root("pid-round-trip");
        let mut written = metadata(&root);
        written.pid = 4321;
        save_runtime(&root, &written).expect("saved");

        let read = load_runtime(&root).expect("read").expect("present");

        assert_eq!(read.pid, 4321);
    }

    #[test]
    fn metadata_written_before_pids_were_recorded_still_loads() {
        // Older runtime files have no `pid`. Refusing them would strand a
        // project on an Agent nothing could adopt or replace.
        let root = temporary_root("pid-absent");
        let path = runtime_path(&root);
        fs::create_dir_all(path.parent().expect("parent")).expect("dir");
        fs::write(
            &path,
            format!(
                r#"{{"schema_version":"{}","bind_addr":"127.0.0.1:43210","token":"{}","project_root":"{}"}}"#,
                AGENT_RUNTIME_SCHEMA,
                "a".repeat(64),
                root.to_string_lossy()
            ),
        )
        .expect("write");

        let read = load_runtime(&root).expect("read").expect("present");

        assert_eq!(read.pid, 0);
    }

    #[test]
    fn supervising_the_same_agent_twice_records_it_once() {
        // `agent_start` adopts on one path and spawns on another; both reach
        // here, and signalling a pid twice on quit is a race against reuse of
        // that number by an unrelated process.
        let before = SUPERVISED.lock().expect("lock").len();
        supervise(999_001);
        supervise(999_001);

        let recorded = SUPERVISED.lock().expect("lock");
        assert_eq!(recorded.iter().filter(|pid| **pid == 999_001).count(), 1);
        assert_eq!(recorded.len(), before + 1);
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
