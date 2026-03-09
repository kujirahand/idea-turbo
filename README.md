# 楽しくブレストするツール「idea-turbo」

このプロジェクトは、アイデアをブレストするためのツール「idea-turbo」を開発するためのプロジェクトです。

「idea-turbo」は、ユーザーが入力したキーワードやテーマに基づいて、ユーザーが一人でアイデアを出すのを助けるツールです。ローカルLLMを使って、ユーザーが入力したアイデアを、全力で褒めまくります。

ユーザーのアイデアが尽きたときには、ユーザーが入力したキーワードやテーマに関連するアイデアを生成して、ユーザーのアイデア出しを助けます。

このプロジェクト当初のコンセプトは、[こちらのマイナビさまの連載](https://news.mynavi.jp/techplus/article/zerovibecoding-16/)で解説しています。

## 使用する技術

- Ollama
  - 設定ファル「setting.toml」で、モデルの変更や、プロンプトの変更ができます
- Python
  - コーディングエージェントの実装に使用します
  - FastAPI - ローカルWebサーバーの実装に利用します

## インストールと実行手順

最初に、ローカルLLMを使うために、[Ollama](https://ollama.com/)をインストールします。

続いて、リポジトリをクローンして、必要なライブラリをインストールし、アプリを実行してください。

```sh
# リポジトリをクローン
git clone https://github.com/kujirahand/idea-turbo.git
cd idea-turbo
# ライブラリのインストール
pip install -r requirements.txt
# アプリの実行
python main.py
```

### メモ

バイブコーディングで作成しました。[こちらが仕様書](AGENTS.md)です。
