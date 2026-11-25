// EDEN-VK99II「幻映」Tauri 壳
// 职责: 拉起/回收 Python 引擎 sidecar (uv run), 原生文件对话框, 端口透出.
// 拖动/渲染全部交给 WebView2 + 原生标题栏 — 彻底绕开 Tk 的模态拖拽重绘坑.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU16, Ordering};
use std::sync::Mutex;
use tauri::Manager;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

static PORT: AtomicU16 = AtomicU16::new(0);

// ---------- 落盘日志: 软件根目录/log, 写不进退到 LOCALAPPDATA/EDEN/log ----------
fn log_file() -> Option<&'static std::path::Path> {
    use std::path::PathBuf;
    static CACHE: std::sync::OnceLock<Option<PathBuf>> = std::sync::OnceLock::new();
    CACHE
        .get_or_init(|| {
            let mut cands: Vec<PathBuf> = vec![];
            if let Ok(exe) = std::env::current_exe() {
                if let Some(dir) = exe.parent() {
                    cands.push(dir.join("log"));
                }
            }
            if let Ok(la) = std::env::var("LOCALAPPDATA") {
                cands.push(PathBuf::from(la).join("EDEN").join("log"));
            }
            for d in cands {
                if std::fs::create_dir_all(&d).is_ok() {
                    let day = chrono::Local::now().format("%Y%m%d");
                    return Some(d.join(format!("eden_shell_{day}.log")));
                }
            }
            None
        })
        .as_deref()
}

fn shell_log(msg: &str) {
    use std::io::Write;
    let Some(p) = log_file() else { return };
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(p) {
        let _ = writeln!(
            f,
            "[{}] {msg}",
            chrono::Local::now().format("%Y-%m-%d %H:%M:%S")
        );
    }
}

#[derive(Default)]
struct App {
    child: Mutex<Option<Child>>,
}

fn find_engine_root() -> Option<String> {
    // 安装版: NSIS 把 resources 的 engine/*.py 放到 exe 同级或 resources 子目录
    let exe = std::env::current_exe().ok()?;
    let dir = exe.parent()?;
    for sub in ["engine", "resources\\engine", "resources", ""] {
        let cand = if sub.is_empty() {
            dir.to_path_buf()
        } else {
            dir.join(sub)
        };
        if cand.join("vk99_server.py").exists() {
            return Some(cand.to_string_lossy().into_owned());
        }
    }
    None
}

fn root_dir() -> String {
    std::env::var("EDEN_ROOT")
        .ok()
        .or_else(find_engine_root)
        .unwrap_or_else(|| r"C:\Users\Lingy\vk99screen".to_string())
}

fn probe_existing_sidecar() -> Option<u16> {
    // 单实例护栏: 已有幻映引擎在 8793~8812 活着就直接复用它的端口.
    // 双实例并发转码会抢写同一 prev_cache 产出坏文件 (预览黑屏元凶之一).
    use std::io::{Read, Write};
    use std::net::TcpStream;
    use std::time::Duration;
    for p in 8793u16..=8812 {
        // connect_timeout 硬性封顶: 本机某些防火墙/代理规则会 DROP loopback SYN,
        // 普通 connect() 每口阻塞约 2s, 20 口 = 40s (实测就是启动慢的元凶).
        let addr = format!("127.0.0.1:{}", p).parse().unwrap();
        if let Ok(mut s) = TcpStream::connect_timeout(&addr, Duration::from_millis(100)) {
            let _ = s.set_read_timeout(Some(Duration::from_millis(120)));
            let _ = s.set_write_timeout(Some(Duration::from_millis(120)));
            if s.write_all(b"GET /api/state HTTP/1.0\r\n\r\n").is_ok() {
                let mut buf = [0u8; 512];
                if let Ok(n) = s.read(&mut buf) {
                    let t = String::from_utf8_lossy(&buf[..n]);
                    if t.contains("200 OK") && t.contains("\"phase\"") {
                        return Some(p);
                    }
                }
            }
        }
    }
    None
}

fn eden_venv_python() -> Option<std::path::PathBuf> {
    // 常驻引擎环境: 首次后台建好, 之后每次启动直接用它, 省掉 uv run 现建环境(3~6s)
    let la = std::env::var("LOCALAPPDATA").ok()?;
    Some(std::path::PathBuf::from(la)
        .join("EDEN")
        .join("venv")
        .join("Scripts")
        .join("python.exe"))
}

fn ensure_venv() {
    // 后台补建 venv, 下次启动即走快路径; 失败无妨 (继续走 uv run 兼容路径)
    let Some(py) = eden_venv_python() else { return };
    if py.exists() {
        return;
    }
    let Some(dir) = py.parent().and_then(|p| p.parent()) else { return };
    let _ = std::fs::create_dir_all(dir);
    let d = dir.to_string_lossy().to_string();
    let p = py.to_string_lossy().to_string();
    let mk = Command::new("cmd")
        .args(["/C", "uv", "venv", &d, "--python", "3.12"])
        .env("CARGO_HTTP_PROXY", "")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();
    if !mk.map(|mut c| c.wait().map(|s| s.success()).unwrap_or(false)).unwrap_or(false) {
        return;
    }
    let _ = Command::new("cmd")
        .args([
            "/C", "uv", "pip", "install", "--python", &p,
            "--default-index", "https://mirrors.aliyun.com/pypi/simple",
            "opencv-python", "pillow", "numpy", "websocket-client",
        ])
        .env("CARGO_HTTP_PROXY", "")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map(|mut c| c.wait());
}

fn attach_port_reader(mut child: Child, state: &App) {
    if let Some(out) = child.stdout.take() {
        std::thread::spawn(move || {
            let rd = BufReader::new(out);
            for line in rd.lines().flatten() {
                if let Some(v) = line.strip_prefix("EDEN_PORT=") {
                    if let Ok(p) = v.parse::<u16>() {
                        PORT.store(p, Ordering::SeqCst);
                    }
                }
            }
        });
    }
    // 引擎 stderr 逐行落盘: 线程崩、traceback 这类只在 stderr 冒的东西从此留痕
    if let Some(err) = child.stderr.take() {
        std::thread::spawn(move || {
            let rd = BufReader::new(err);
            for line in rd.lines().flatten() {
                shell_log(&format!("[engine-stderr] {line}"));
            }
            shell_log("sidecar stdout/stderr closed (process exited or crashed)");
        });
    }
    *state.child.lock().unwrap() = Some(child);
}

fn spawn_sidecar(state: &App) {
    let root = root_dir();
    // 快路径: 常驻 venv 直接起 (启动 ~0.5s)
    if let Some(py) = eden_venv_python() {
        if py.exists() {
            let mut cmd = Command::new(&py);
            // 传一个 .ico 当 argv[0]: python 原生加载图标 → CPython 跳过 pyw 单步加载器,
            // 不再 fork 第二个解释器 (实测省 ~40s 的二次安装器启动)
            let tray_ic = std::path::Path::new(&root).join("EDEN.ico");
            // -B: 不写 __pycache__ (装进 Program Files 会留垃圾+首启写缓存拖慢)
            if tray_ic.exists() {
                cmd.args(["-B", "-u", "vk99_server.py"]);
            } else {
                cmd.args(["-u", "vk99_server.py"]);
            }
            cmd.current_dir(&root)
                .env("EDEN_PPID", std::process::id().to_string())
                .env("EDEN_ARGV0_TRAY", &tray_ic)
                .stdin(Stdio::null())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped());
            #[cfg(windows)]
            cmd.creation_flags(CREATE_NO_WINDOW);
            match cmd.spawn() {
                Ok(child) => {
                    shell_log(&format!("engine spawned via persistent venv, pid={:?}", child.id()));
                    attach_port_reader(child, state);
                    return;
                }
                Err(e) => shell_log(&format!("venv fast path failed: {e}, trying uv fallback")),
            }
        }
    }
    // 中位路径: 随包便携 Python (1.2.1 起, 新机首启零依赖, 不再赌用户装没装 uv)
    let root_pb = std::path::PathBuf::from(&root);
    for cand in [root_pb.join("runtime"), root_pb.join("engine").join("runtime")] {
        let py = cand.join("python.exe");
        if py.exists() {
            let mut cmd = Command::new(&py);
            cmd.args(["-B", "-u", "vk99_server.py"])
                .current_dir(&root)
                .env("EDEN_PPID", std::process::id().to_string())
                .stdin(Stdio::null())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped());
            #[cfg(windows)]
            cmd.creation_flags(CREATE_NO_WINDOW);
            match cmd.spawn() {
                Ok(child) => {
                    shell_log(&format!(
                        "engine spawned via bundled runtime, pid={:?} ({})",
                        child.id(),
                        py.display()
                    ));
                    attach_port_reader(child, state);
                    return;
                }
                Err(e) => shell_log(&format!("bundled runtime spawn failed: {e}")),
            }
        }
    }
    // 兼容路径: uv 现建 ephemeral env (仅开发态/极端情况; 需要本机有 uv)
    shell_log("uv fallback path (requires uv installed on this machine)");
    let mut cmd = Command::new("cmd");
    cmd.current_dir(&root)
        .args([
            "/C",
            "uv",
            "run",
            "--python",
            "3.12",
            "--default-index",
            "https://mirrors.aliyun.com/pypi/simple",
            "--with",
            "opencv-python",
            "--with",
            "pillow",
            "--with",
            "numpy",
            "--with",
            "websocket-client",
            "python",
            "-u",
            "vk99_server.py",
        ])
        .env("EDEN_PPID", std::process::id().to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    let child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            shell_log(&format!("FATAL sidecar spawn failed (uv path): {e}"));
            eprintln!("sidecar spawn failed: {e}");
            return;
        }
    };
    shell_log("engine spawned via uv fallback");
    attach_port_reader(child, state);
    std::thread::spawn(ensure_venv);
}

fn kill_sidecar(state: &App) {
    // 只 kill 直接子进程(uv wrapper): vk99_server 的 parent_watchdog 阻塞在
    // EDEN_PPID 上, 壳一死引擎立刻自杀, 不会留孤儿. 旧的 curl /api/quit 要在
    // 主线程同步等 cmd+curl (端口死时卡满 -m 2 秒), 正是关窗卡顿的元凶, 已移除.
    if let Some(c) = state.child.lock().unwrap().as_mut() {
        shell_log("shell exiting, killing sidecar");
        let _ = c.kill();
    }
}

#[tauri::command]
async fn pick_file() -> Option<String> {
    // spawn_blocking: rfd 是阻塞模态对话框, 同步命令会卡死主线程 → 点「选择素材」后 UI 转圈半天的元凶
    tauri::async_runtime::spawn_blocking(|| {
        rfd::FileDialog::new()
            .set_title("选择视频 / 图片素材")
            .add_filter(
                "视频/图片",
                &["mp4", "avi", "mov", "mkv", "webm", "gif", "png", "jpg", "jpeg"],
            )
            .pick_file()
            .map(|p| p.to_string_lossy().into_owned())
    })
    .await
    .ok()
    .flatten()
}

#[tauri::command]
fn sidecar_port() -> u16 {
    PORT.load(Ordering::SeqCst)
}

fn main() {
    // 闪退留痕: 任何 panic 先写进 log 再走默认处理
    std::panic::set_hook(Box::new(|info| {
        shell_log(&format!("FATAL panic: {info}"));
    }));
    shell_log("== EDEN shell start ==");
    tauri::Builder::default()
        .manage(App::default())
        .setup(|app| {
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let t0 = std::time::Instant::now();
                let state = handle.state::<App>();
                if let Some(p) = probe_existing_sidecar() {
                    PORT.store(p, Ordering::SeqCst);
                    shell_log(&format!(
                        "reusing existing engine at :{p} 的引擎 (probe {}ms)",
                        t0.elapsed().as_millis()
                    ));
                } else {
                    shell_log(&format!(
                        "probe miss ({}ms), spawning sidecar",
                        t0.elapsed().as_millis()
                    ));
                    spawn_sidecar(&state);
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![pick_file, sidecar_port])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let state = window.state::<App>();
                kill_sidecar(&state);
            }
        })
        .run(tauri::generate_context!())
        .unwrap_or_else(|e| {
            shell_log(&format!("FATAL shell startup failed: {e}"));
            panic!("EDEN 启动失败: {e}");
        });
}
