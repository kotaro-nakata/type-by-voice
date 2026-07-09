# Windows 対応 実装計画（クロスプラットフォーム化）

`voice-term` を **1 つのコードベースで Linux / Windows 両対応**にするための計画。
方針は「OS 依存部分だけをプラットフォーム層に切り出し、コア（録音・文字起こし・
ホットキー）は共通のまま」。既存の "小さくハック可能な 2 ファイル" という思想を
できるだけ壊さない。

---

## 1. 現状の OS 依存箇所（棚卸し）

| # | 機能 | 現状の実装 | 該当箇所 |
|---|------|-----------|---------|
| 1 | 文字入力 / 貼り付け | `xdotool` / `wtype` / `ydotool` / `xclip` を subprocess 呼び出し | `voice_term.py:123-204` (`Outputter`) |
| 2 | トレイアイコン | GTK `AyatanaAppIndicator3` の別プロセスヘルパー | `voice_term.py:567-596`, `tray_indicator.py` 全体 |
| 3 | 多重起動防止 | `fcntl.flock` | `voice_term.py:675-688` |
| 4 | CUDA/cuDNN ロード | `.so` を glob して `ctypes.CDLL` で preload | `voice_term.py:624-663` |
| 5 | 一時 / ランタイムディレクトリ | `XDG_RUNTIME_DIR` / `/tmp` 前提 | `voice_term.py:370, 679`, `tray_indicator.py:62-71` |
| 6 | デスクトップ通知 | `notify-send` | `voice_term.py:34-47` |
| 7 | 終了シグナル | `signal.SIGTERM` | `voice_term.py:613`, `tray_indicator.py:249,263` |
| 8 | ホットキー既定値 | `cmd+alt`（Win+Alt） | `config.toml` の `[hotkey] key` |
| 9 | ファイルを開く | `xdg-open` | `tray_indicator.py:74-79` |
| 10 | 設定パス | `~/.config/voice-term/` 固定 | `voice_term.py:32` |

コア（クロスプラットフォームで変更不要）:
- `faster-whisper` / `ctranslate2`（Win 対応）
- `sounddevice`（PortAudio, Win 対応）
- `pynput`（キーボードフック, Win 対応）
- `numpy`, `tomllib`

---

## 2. 設計方針：プラットフォーム抽象化レイヤ

新規ファイル **`platform_backend.py`** を追加し、OS 依存の実装をここに集約する。
`voice_term.py` は `sys.platform` を直接見ず、この層の関数/クラスを呼ぶだけにする。

```
platform_backend.py
├── IS_WINDOWS / IS_MAC / IS_LINUX          # sys.platform 判定
├── runtime_dir() -> Path                    # #5 一時/状態ファイル置き場
├── config_dir()  -> Path                    # #10 設定ディレクトリ
├── notify(summary, body, timeout_ms)        # #6 通知
├── open_path(path)                          # #9 ファイルを既定アプリで開く
├── acquire_single_instance() -> handle      # #3 多重起動防止
├── preload_accel_libs()                     # #4 CUDA ライブラリ
└── make_injector(method, trailing) -> TextInjector   # #1 文字入力
```

トレイ（#2）は別ファイルのまま `pystray` ベースに置き換える（後述）。

---

## 3. 各項目の実装詳細

### #1 文字入力 / 貼り付け（最重要）
現行の `Outputter` を `platform_backend` の `TextInjector` サブクラスに分離。

- **共通 API**: `send(text)`, `warn_if_missing()`
- **Linux 実装**: 既存の `Outputter` ロジックをそのまま移植（X11/Wayland 判定）。
- **Windows 実装**:
  - クリップボードコピー → `pyperclip`（依存追加）。
  - 貼り付け → `pynput` の `keyboard.Controller` で Ctrl+V を送出。
    subprocess を使わず同一プロセスで完結できる。
  - `method="type"`（直接タイプ）→ `keyboard.Controller().type(text)`。
    ただし日本語は取りこぼしやすいので **既定は `paste` 推奨**（README に明記）。
  - 貼り付け前に、押されているホットキー修飾キーが完全に離れるまで少し待つ
    （既存の `time.sleep(0.05)` を踏襲、必要なら延長）。
- 注意: Ctrl+V を送る際、ユーザーがまだ修飾キー（Alt など）を握っている場合の
  誤爆を避けるため、`pynput.Controller` で明示的に modifier を離してから送る実装を検討。

### #2 トレイアイコン（クロスプラットフォーム化）
GTK/AppIndicator は Windows で動かないため **`pystray` + `Pillow`** に置換。
`pystray` は Windows / Linux(AppIndicator or XEmbed) / macOS すべて対応。

- `tray_indicator.py` を書き換え（or `tray_pystray.py` を新設して差し替え）。
- アイコン描画（`make_static_icon` / `make_recording_frame`）は Pillow ベースなので
  **ほぼ流用可能**。`pystray.Icon.icon = image` で差し替えるループに移植。
- 状態ファイルのポーリング方式（`state` ファイルを読む IPC）は現行踏襲。
- Windows ではメインプロセス内スレッドで pystray を回す構成も可能（別プロセスの
  `os.kill(pid,0)` 生存監視が Win では使いにくいため）。**推奨: 同一プロセス・
  別スレッドで tray を動かす**方式に統一し、`_start_tray` を簡素化。
  - ただし pystray は「メインスレッドで動かす」制約が OS によりある点に注意。
    → メインループ設計を見直す（後述の懸念点参照）。
- リップル（sonar 波紋）アニメーションは、アイコン画像を数百 ms ごとに差し替える
  方式で再現。フレームレートは Win のトレイ更新負荷を見て調整。

### #3 多重起動防止
`acquire_single_instance()` に分岐:
- **Linux**: 既存 `fcntl.flock`。
- **Windows**: `msvcrt.locking()` によるロック、または名前付きミューテックス
  （`ctypes` で `CreateMutexW` → `ERROR_ALREADY_EXISTS` 判定）。
  実装が単純な `msvcrt` を第一候補にする。

### #4 CUDA / cuDNN ライブラリのロード
`preload_accel_libs()` に分岐:
- **Linux**: 既存の `.so` glob + `ctypes.CDLL(RTLD_GLOBAL)`。
- **Windows**:
  - `.so` ではなく `.dll`。`nvidia-*` の pip パッケージ内 `bin/` にある DLL を
    `os.add_dll_directory()` で検索パスに追加する（Python 3.8+）。
  - CPU 運用時は nvidia パッケージが無いので no-op（現行同様）。
  - **今回の第一目標は CPU 運用**（前回の合意）。GPU は後続タスクとし、
    Windows GPU 経路は「動けばラッキー、要検証」の位置づけにする。

### #5 一時 / ランタイムディレクトリ
`runtime_dir()`:
- **Linux**: `XDG_RUNTIME_DIR` → 無ければ `/tmp`（現行踏襲）。
- **Windows**: `tempfile.gettempdir()`（≒ `%LOCALAPPDATA%\Temp`）配下に
  `voice-term/`。
- 状態ファイル / ロックファイル / アイコン PNG 出力先をすべてこの関数経由に統一。

### #6 デスクトップ通知
`notify()`:
- **Linux**: 既存 `notify-send`。
- **Windows**:
  - 軽量にするなら **通知はコンソール出力のみ + tray ツールチップ**で代替し、
    OS トースト依存を避ける（追加依存ゼロ）。← 推奨
  - トーストが欲しい場合は `winotify` などを任意依存に。まずは無しで進める。

### #7 終了シグナル
- `SIGTERM` は Windows に無い。tray からの終了は **プロセス内イベント
  （`threading.Event` / 直接 `App.shutdown()` 呼び出し）**で行う設計に変更。
  tray を同一プロセス・別スレッド化（#2）すれば `os.kill` / `SIGTERM` 不要になり、
  Linux/Win 両方で綺麗になる。
- `SIGINT`（Ctrl+C）は両対応なので維持。

### #8 ホットキー既定値
- Windows では **Win キーは OS が横取り**するため `cmd+alt` は不安定。
- 既定を OS ごとに出し分ける:
  - Linux: `cmd+alt`（現状維持）
  - Windows: `ctrl+alt`（もしくは `f9` 等の単一キー）
- `DEFAULT_CONFIG` 内にコメントで OS 別の推奨を追記。
  実装上は `load_config()` 生成時に OS を見て既定 `key` を差し替える。

### #9 ファイルを開く（tray メニュー）
`open_path()`:
- **Linux**: `xdg-open`
- **Windows**: `os.startfile(path)`

### #10 設定パス
`config_dir()`:
- **Linux**: `~/.config/voice-term/`（現行）
- **Windows**: `%APPDATA%\voice-term\`（`os.environ["APPDATA"]`）
- `CONFIG_PATH` をこの関数経由に変更。tray 側の `_config_path()` も統一。

---

## 4. 依存関係の変更（requirements）

`requirements.txt` を base + OS 別に整理:

```
# --- 共通 ---
faster-whisper>=1.0.3
sounddevice>=0.4.6
numpy>=1.26
pynput>=1.7.6
pystray>=0.19          # ← 追加（クロスプラットフォーム tray）
Pillow>=10             # ← tray 描画（従来 system python 依存だったのを明示）

# --- Windows のみ ---
pyperclip>=1.8 ; sys_platform == "win32"   # ← 追加（クリップボード）

# --- GPU（任意 / Linux 主） ---
nvidia-cublas-cu12 ; sys_platform == "linux"
nvidia-cudnn-cu12>=9.0 ; sys_platform == "linux"
```

Windows GPU 版の nvidia パッケージは後続タスクで検証してから追記。

---

## 5. 起動方法（Windows）

- `voice-term` シェルスクリプト / `install-desktop.sh` は Linux 専用。
- Windows 向けに **`run_windows.bat`**（or PowerShell スクリプト）を新設:
  - venv の python で `voice_term.py` を起動。
  - コンソール非表示で起動したい場合は `pythonw.exe` を使用。
- ドキュメントに「`py -m venv .venv` → `pip install -r requirements.txt` →
  `pythonw voice_term.py`」の手順を追記。

---

## 6. 想定される懸念・要検証ポイント

1. **pystray のメインスレッド制約**: 一部バックエンドで `Icon.run()` はメイン
   スレッド必須。現行の「メインは待機ループ、tray は別プロセス」を
   「tray をメインスレッド、アプリロジックを別スレッド」に反転する必要が
   あるかもしれない。→ 起動シーケンスの再設計が最大の作業ポイント。
2. **Windows でのグローバルホットキー**: `pynput` のフックが管理者権限や
   特定アプリ前面時に効かないケース。要実機確認。
3. **貼り付けの信頼性**: Ctrl+V 送出タイミング / IME 状態依存。日本語入力時の
   取りこぼしを実機で確認。
4. **PortAudio デバイス**: Windows のデフォルト入力デバイス選択挙動の差異。
5. **文字コード**: Windows のコンソール出力（cp932）で絵文字 print が化ける/
   例外になる可能性 → `sys.stdout` を UTF-8 化 or ログ側で対処。

---

## 7. 実装フェーズ（Phase / Step）

### Phase 1: プラットフォーム基盤層の新設
- [x] **Step 1-1**: `platform_backend.py` を新設 — `IS_WINDOWS` / `IS_LINUX` 判定、
      `runtime_dir()`(#5)、`config_dir()`(#10) を実装
- [x] **Step 1-2**: `notify()`(#6) / `open_path()`(#9) を移設し OS 分岐
- [x] **Step 1-3**: `acquire_single_instance()`(#3) を移設 —
      Linux: `fcntl` / Windows: `msvcrt.locking`
- [x] **Step 1-4**: `preload_accel_libs()`(#4) を移設 —
      Linux: 既存 `.so` preload / Windows: `os.add_dll_directory()`（CPU時 no-op）

### Phase 2: 文字入力レイヤ（TextInjector）
- [x] **Step 2-1**: `Outputter` を `platform_backend` の `TextInjector` 基底 +
      `LinuxInjector`（既存ロジック移植）に分離
- [x] **Step 2-2**: `WindowsInjector` を実装 — `pyperclip` コピー +
      `pynput.Controller` で Ctrl+V 送出（modifier 解放処理込み）
- [x] **Step 2-3**: `voice_term.py` から `make_injector()` 経由で利用するよう差し替え

### Phase 3: トレイ & 起動シーケンス再設計
- [x] **Step 3-1**: `tray_indicator.py` を `pystray` + `Pillow` ベースに書き換え
      （アイコン描画・波紋アニメは流用）
- [x] **Step 3-2**: tray を同一プロセス・別スレッド構成に変更し、
      `SIGTERM`/`os.kill` ベースの終了(#7)をプロセス内イベントに置換
- [x] **Step 3-3**: `App.run()` の起動シーケンスを再設計
      （pystray のメインスレッド制約への対応）

### Phase 4: 設定・依存・起動スクリプト
- [x] **Step 4-1**: OS 別の既定ホットキー(#8) — Windows は `ctrl+alt`
- [x] **Step 4-2**: `requirements.txt` を OS 別マーカー付きに整理
      （`pystray` / `Pillow` / `pyperclip` 追加）
- [x] **Step 4-3**: `run_windows.bat` 新設 + README に Windows 手順を追記

### Phase 5: 検証
- [x] **Step 5-1**: Linux での回帰確認（起動→録音→変換→貼り付け→tray→終了）
- [x] **Step 5-2a**: Windows 実機での動作確認チェックリスト作成（→ §8）
- [ ] **Step 5-2b**: Windows 実機での動作確認 実施
      （※ユーザーの Windows 環境で §8 のチェックリストに沿って実施）

---

## 8. Windows 実機 動作確認チェックリスト（Phase 5-2）

Windows 10/11 の実機で以下を確認する:

### セットアップ
- [ ] `run_windows.bat` のダブルクリックで venv 作成〜依存インストールが完走する
- [ ] 2回目以降の起動はインストールをスキップして即起動する
- [ ] コンソールウィンドウが表示されずに起動する（pythonw）
- [ ] `%APPDATA%\voice-term\config.toml` が自動生成され、`key = "ctrl+alt"` になっている

### 基本動作
- [ ] トレイに灰色ドット（読込中）→ 緑ドット（待機中）と遷移する
- [ ] Ctrl+Alt 長押しで赤ドット＋波紋アニメーションになる
- [ ] 日本語を話す → 離す → フォーカス中のアプリに日本語が貼り付けられる
- [ ] 英語を話す → 英語が貼り付けられる（言語自動判定）
- [ ] メモ帳 / ブラウザ / VS Code など複数アプリで貼り付けが機能する
- [ ] IME が ON の状態でも貼り付けが化けない
- [ ] `method = "clipboard"` にするとコピーのみになる

### トレイメニュー
- [ ] 「状態: 〜」表示が状態に追従する
- [ ] 「設定を開く」で config.toml が開く
- [ ] 「ログを開く」でログが開く（run_windows.bat 起動時）
- [ ] 「終了」でプロセスが完全に終了する（タスクマネージャで確認）

### エッジケース
- [ ] 2重起動すると2つ目が「すでに起動しています」で終了する
- [ ] 0.3 秒未満の短い録音は無視される
- [ ] Ctrl+Alt を含む他アプリのショートカットと干渉しないか確認
  （干渉する場合は config で `f9` などに変更して回避できること）

### 既知の制限（確認のみ）
- GPU (CUDA) は未対応（CPU/int8 で動作）。速度が不足する場合は
  config の `name` を `"medium"` や `"small"` に変更する。
- トースト通知なし（トレイ表示のみ）。

---

## 9. スコープ外（今回やらない）

- Windows での GPU (CUDA) 推論の本格対応 … 後続タスク。
- macOS 対応 … 抽象化の恩恵で入れやすくなるが今回は対象外。
- インストーラ（exe 化 / PyInstaller）… 需要が出たら別途。
