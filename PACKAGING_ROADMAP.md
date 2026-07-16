# VoiceTerm デスクトップ配布ロードマップ

## 1. 目的

VoiceTerm を、Python・Git・コマンド操作を知らない利用者でもインストールして
使えるデスクトップアプリとして配布する。

最終的な配布物は次を想定する。

| OS | 主な配布物 | 利用者の操作 |
|---|---|---|
| Windows 10/11 (x64) | `VoiceTerm-Setup-x64.exe` | ダウンロードしてインストーラーを実行 |
| macOS (Apple Silicon / Intel) | `VoiceTerm-*.dmg` | DMGを開き、Applicationsへ移動 |
| Ubuntu Linux (x64) | `VoiceTerm-*.deb` | ダウンロードしてソフトウェアセンターでインストール |
| その他のLinux | `VoiceTerm-*.AppImage`（後続） | ダウンロードして直接実行 |

GitHub Releasesを最初の配布先とし、タグを作成すると各OS向け成果物が自動生成
される状態を目指す。

## 2. 現状

- Linuxではソースコード、venv、OSパッケージを利用して動作する。
- Windowsではソースから動作し、Windows固有の貼り付け、トレイ、CUDA DLL処理がある。
- macOSはOS判定だけ存在し、設定パス、貼り付け、メニューバー、権限導線などは未実装。
- Whisperモデルは初回利用時にダウンロードされる。
- Python本体と依存ライブラリを含んだ配布用アプリはまだない。
- コード署名、公証、自動リリースはまだない。

「アプリを各OSで動かす対応」と「ユーザー向けインストーラーを作る対応」は分けて
進める。動作未確認のOS向け成果物を正式版として公開しない。

## 3. 基本方針

### 3.1 Pythonアプリのバンドル

PyInstallerを使用し、PythonインタープリターとPython依存関係を含む自己完結型の
アプリフォルダを作る。初期段階では、問題を調査しやすい `onedir` 形式を使う。
安定後も、巨大なネイティブ依存関係を持つ本アプリでは、単一実行ファイルより
`onedir` をOS標準のインストーラーで包む方式を基本とする。

PyInstallerの成果物はOSとCPUアーキテクチャに依存するため、各OS上で個別に
ビルドする。クロスコンパイルは前提にしない。

### 3.2 インストーラー

- Windows: PyInstallerの成果物をInno Setupで `Setup.exe` にする。
- macOS: `.app` を生成し、署名・公証して `.dmg` にする。
- Ubuntu: PyInstallerの成果物を `.deb` にする。
- AppImage / Flatpak / Store公開は、基本配布が安定した後に検討する。

### 3.3 モデルとGPUランタイム

- 約1.5 GBのWhisperモデルはインストーラーに同梱しない。
- 初回起動時にダウンロードし、OS標準のユーザーデータ領域へキャッシュする。
- 将来、ダウンロード進捗、モデル選択、再試行、削除機能を追加する。
- NVIDIA CUDA/cuDNNを含めるGPU版はサイズが大きいため、CPU版との分離も検討する。
- macOSではCUDAを利用せず、CPU向け設定を基本とする。

### 3.4 安全な開発方法

- 配布作業は専用ブランチで行い、既存の動作ブランチを保持する。
- 文書、バンドル、インストーラー、自動化を小さいコミットに分ける。
- 最初から署名付き正式版にせず、署名なしベータ版で実機動作を確認する。
- GitHub Actionsの秘密情報はSecretsに保存し、証明書や鍵をコミットしない。
- リリースは通常のpushでは行わず、明示的なバージョンタグを起点にする。
- 生成物（`build/`, `dist/`）はGit管理しない。

## 4. 利用者体験

### Windows

1. `VoiceTerm-Setup-x64.exe` をダウンロードする。
2. インストーラーを実行する。
3. スタートメニューからVoiceTermを起動する。
4. 初回のみ音声認識モデルをダウンロードする。
5. タスクトレイに常駐し、ホットキーで音声入力する。

Python、pip、Git、venvは不要とする。アンインストーラーも提供する。

### macOS

1. `VoiceTerm-arm64.dmg` または `VoiceTerm-x64.dmg` をダウンロードする。
2. VoiceTermをApplicationsへドラッグする。
3. 初回起動時にマイク、アクセシビリティ、入力監視を許可する。
4. 初回のみモデルをダウンロードする。
5. メニューバーに常駐し、ホットキーで音声入力する。

### Linux

1. Ubuntuでは `.deb` をダウンロードする。
2. ソフトウェアセンターまたは `apt` でインストールする。
3. アプリ一覧からVoiceTermを起動する。
4. 初回のみモデルをダウンロードする。

X11 / Wayland、クリップボード、AppIndicatorなどのOS依存パッケージは、可能な限り
`.deb` の依存関係として宣言する。

## 5. 実装フェーズ

### Phase 0: 配布基盤の設計と再現性

- [x] 配布方針とロードマップを文書化する。
- [x] アプリ名、実行ファイル名、バージョンの唯一の定義元を作る。
- [x] `build` / `dist` / インストーラー出力を `.gitignore` に追加する。
- [x] 通常依存とビルド依存を分離する。
- [x] PyInstaller specを追加する。
- [x] ローカルビルド用スクリプトを追加する。

完了条件: Linux上で `dist/VoiceTerm/` が生成され、少なくとも起動前の構成検査を
再現できること。

### Phase 1: Windowsベータ版

- [ ] Windows向けPyInstallerビルドを成功させる。
- [ ] `faster-whisper`, `ctranslate2`, `sounddevice`, `pystray`, Pillow、アイコンを含める。
- [ ] CUDA/cuDNN DLLの収集とロードを検証する。
- [x] Inno Setup定義を追加する（Windows CI／実機でのコンパイル確認は未完了）。
- [ ] スタートメニュー、デスクトップショートカット、自動アンインストールを実装する。
- [ ] Windows 10/11実機でCPU/GPU、マイク、トレイ、貼り付けを確認する。

完了条件: Python未導入のWindows PCでインストール、起動、文字起こし、貼り付け、
終了、アンインストールができること。

### Phase 2: macOS対応とベータ版

- [ ] `MacInjector` を追加し、クリップボードと `Cmd+V` を実装する。
- [ ] macOS標準の設定・ログ・キャッシュパスを使用する。
- [ ] `open`、通知、単一起動、メニューバー処理を実装する。
- [ ] マイク利用目的を `Info.plist` に設定する。
- [ ] アクセシビリティ／入力監視権限の検出と案内を実装する。
- [ ] `.icns` アイコンと `.app` バンドルを生成する。
- [ ] Apple Silicon版とIntel版を実機確認する。

完了条件: Python未導入のMacでインストール、権限付与、起動、文字起こし、貼り付け、
終了ができること。

### Phase 3: Linuxパッケージ

- [ ] Ubuntu向けPyInstallerビルドを確認する。
- [ ] `.desktop`、アイコン、依存関係を含む `.deb` を生成する。
- [ ] UbuntuのX11とWaylandで確認する。
- [ ] AppImageの実現性を検証する。

完了条件: サポート対象Ubuntuで `.deb` をダブルクリックして導入できること。

### Phase 4: CI/CDと正式リリース

- [ ] GitHub ActionsにWindows / macOS / Ubuntuのビルドジョブを追加する
      （Windows / Ubuntuの土台は追加済み、macOSは対応実装後に追加）。
- [ ] pull requestではビルド検証のみを行う。
- [ ] `vX.Y.Z` タグでGitHub Releaseと成果物を作る。
- [ ] SHA-256チェックサムを添付する。
- [ ] Windowsコード署名を導入する。
- [ ] macOS Developer ID署名、Hardened Runtime、公証、stapleを導入する。
- [ ] リリースノートと既知の問題を掲載する。

完了条件: タグから再現可能な署名済み成果物が生成されること。

### Phase 5: 配布後の改善

- [ ] アプリ内アップデートまたは更新通知を検討する。
- [ ] 初回セットアップ画面、モデル選択、進捗表示を実装する。
- [ ] クラッシュログの安全な収集方法を検討する（明示的な同意を前提とする）。
- [ ] Microsoft Store、Homebrew Cask、Flatpak等を検討する。
- [ ] ARM Windows、追加Linuxディストリビューションを需要に応じて検討する。

## 6. 自動ビルド／リリース構成

GitHub Actionsでは以下のジョブを想定する。

```text
pull request / branch push
  ├─ ubuntu: 構文・単体検査 + Linux bundle smoke test
  ├─ windows: Windows bundle build
  └─ macos: macOS bundle build（macOS対応後に有効化）

vX.Y.Z tag
  ├─ Windows Setup.exe
  ├─ macOS arm64/x64 DMG
  ├─ Ubuntu DEB
  ├─ checksums.txt
  └─ GitHub Release
```

CIのビルド成功だけを動作保証としない。グローバルホットキー、マイク、IME、GPU、
トレイ、OS権限はGUIを持つ実機でリリースチェックを行う。

## 7. バージョニング

Semantic Versioningに近い `MAJOR.MINOR.PATCH` を採用する。

- `0.x.y`: ベータ期間。互換性が変わる可能性がある。
- `1.0.0`: 対象OSで導入・基本操作・アンインストールが安定した時点。
- Gitタグは `v0.1.0` の形式にする。
- アプリ、インストーラー、GitHub Releaseで同じバージョンを使用する。

## 8. 署名と費用

初期のベータ版は署名なしで配布できるが、OSの警告が表示される。

- macOSの一般配布にはApple Developer Program、Developer ID署名、公証が必要。
- Windowsでは信頼された証明書によるAuthenticode署名を推奨する。
- 証明書購入やストア登録は、ベータ版の技術検証後に行う。
- 秘密鍵、証明書パスワード、Apple APIキーはGitHub Secretsで管理する。

## 9. テスト項目

各OSで最低限、以下を確認する。

- クリーン環境へのインストールとアンインストール
- Python未導入環境での起動
- 初回モデルダウンロードと再起動後の再利用
- マイク選択、録音、文字起こし
- 日本語、英語、言語切り替え
- ホットキーの押下／解放と連続使用
- Unicodeを含むクリップボード貼り付け
- トレイ／メニューバーの状態表示と終了
- 多重起動防止
- CPU動作と対応環境でのGPU動作
- オフライン時、権限拒否時、マイクなし、モデル取得失敗時の案内
- OS再起動後のショートカットと設定保持

## 10. 主要リスクと対策

| リスク | 対策 |
|---|---|
| ネイティブライブラリがPyInstallerに収集されない | specで明示し、各OSのクリーン環境で検査する |
| 配布物が巨大になる | モデルを外出しし、将来CPU/GPU版の分離を検討する |
| macOS権限でホットキーや貼り付けが動かない | 権限検出、明確な初回案内、実機テストを行う |
| Windows SmartScreen / macOS Gatekeeper警告 | ベータ後にコード署名・公証を導入する |
| Linuxの環境差 | 最初はUbuntuの限定バージョンを公式サポートする |
| CIではマイクやGUIを検証できない | 自動検査と実機リリースチェックを分ける |
| GPUランタイムのサイズ・互換性 | CPUフォールバックを保持し、対応GPU構成を明記する |

## 11. 最初のマイルストーン

最初のマイルストーンを **`v0.1.0-beta.1`** とし、以下を含める。

- Windows x64の署名なしインストーラー
- Ubuntu x64の開発用バンドル（可能なら `.deb`）
- 再現可能なPyInstaller spec
- GitHub ActionsによるWindows / Ubuntuビルド
- インストール、起動、初回モデル取得、基本操作の手順
- macOSは未完成の成果物を配らず、対応実装を次のマイルストーンで行う

macOS実機とApple Developer資格情報が利用可能になった段階で
**`v0.2.0-beta.1`** としてmacOS版を追加する。
