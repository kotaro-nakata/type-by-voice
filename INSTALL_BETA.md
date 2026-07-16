# VoiceTerm ベータ版インストール手順

## 現在インストールできるもの

| OS | 状態 | インストール方法 |
|---|---|---|
| Windows 10/11 x64 | ベータ版あり | GitHub Actionsからインストーラーを取得 |
| macOS | 未提供 | macOS対応と署名・DMG作成を実装中 |
| Ubuntu Linux | 開発用バンドルのみ | 現時点ではREADMEのソース導入を推奨 |

現在のWindows版は、正式リリース前の動作確認用である。Pythonのインストールは
不要だが、コード署名はまだ行っていない。また、Whisper本体とGPUランタイムを含む
ため、ダウンロードするZIPは約1 GBある。

## Windowsベータ版をインストールする

### 1. GitHub Actionsを開く

次のページを開く。

[Package build — feat/desktop-packaging](https://github.com/kotaro-nakata/type-by-voice/actions/workflows/package-build.yml?query=branch%3Afeat%2Fdesktop-packaging)

成果物のダウンロードにはGitHubへのログインが必要になる場合がある。

### 2. 成功した最新のビルドを選ぶ

一覧から、緑色のチェックが付いた最新の実行を開く。実行名は通常、直近の
コミットメッセージになっている。

画面下部の **Artifacts** セクションまでスクロールする。

### 3. インストーラーをダウンロードする

次の成果物を選ぶ。

```text
VoiceTerm-Windows-Setup-x64
```

似た名前の `VoiceTerm-Windows-x64` は、インストーラー作成前の開発用アプリ
フォルダである。通常の利用者は **Setup** が付いた方を選ぶ。

GitHubからZIPファイルがダウンロードされる。ZIPを展開すると、次のような
インストーラーが入っている。

```text
VoiceTerm-Setup-x64-0.1.0-beta.1.exe
```

CI成果物は14日で期限切れになる。期限切れの場合は、最新の成功した実行を選ぶ。

### 4. インストーラーを実行する

1. ZIPを展開する。
2. `VoiceTerm-Setup-x64-0.1.0-beta.1.exe` をダブルクリックする。
3. インストーラーの案内に従って進める。
4. 必要なら「デスクトップアイコンを作成」を選ぶ。
5. 完了画面からVoiceTermを起動する。

現在はコード署名前のベータ版なので、Windows SmartScreenに
「WindowsによってPCが保護されました」と表示される可能性がある。
自分でこのリポジトリのGitHub Actionsから取得したファイルであることを確認した
うえで、テストする場合は「詳細情報」から実行する。

### 5. 初回起動

起動するとVoiceTermがタスクトレイに常駐する。初回は音声認識モデルを
ダウンロードするため、完了まで数分かかる場合がある。

- ホットキー: **Ctrl + Altを同時に長押し**
- 録音: ホットキーを押したまま話す
- 文字起こし: ホットキーを離す
- 貼り付け: VoiceTermが **Ctrl + Shift + V** を送信
- 終了: タスクトレイのVoiceTermアイコンから「終了」

設定ファイル:

```text
%APPDATA%\voice-term\config.toml
```

ログ:

```text
%LOCALAPPDATA%\voice-term\voice-term.log
```

### 6. アンインストール

Windowsの「設定」→「アプリ」→「インストールされているアプリ」から
VoiceTermを選び、アンインストールする。

## 注意事項

- この成果物は正式リリースではなく、インストールと実機動作を確認するためのもの。
- コード署名がないため、Windowsの警告が表示される可能性がある。
- インストーラー生成の自動テストは成功しているが、配布版でのマイク、GPU、
  ホットキー、IME、貼り付けはWindows実機でも確認する必要がある。
- 初回のモデルダウンロードにはインターネット接続が必要。
- 文字起こし処理そのものはモデル取得後、ローカルで行われる。

## 今後の正式な配布方法

正式版ではGitHub ActionsのArtifactsではなく、リポジトリ右側の
**Releases** からインストーラーを直接ダウンロードできるようにする。
Windows版の実機検証、コード署名、macOS対応が進んだ後に、
`v0.1.0-beta.1` などのリリースとして公開する予定である。

全体計画は [PACKAGING_ROADMAP.md](PACKAGING_ROADMAP.md) を参照。
