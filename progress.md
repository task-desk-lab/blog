# WIP: ハブ記事比較表の品質改善（2026-09-09）

## 目的
「〜おすすめ」ハブ記事15本のmarkdown比較表（不明/—だらけ・スタイル無し）を、
競合（my-best/sakidori/picky-s）分析に基づくfront-matter駆動の比較表に置換。

## 状態: 実装済み・ローカル検証済み・**未コミット/未deploy**

## 変更ファイル（全て task-desk-lab-blog、contentは無変更）
- `layouts/_default/_markup/render-table.html` **新規**: 全markdown表を `.table-scroll` ラップ+`.md-table` クラス付与（横スクロール対応）
- `layouts/partials/hub_compare.html` **新規**: hub_itemsのfront matter（product_name/verdict/best_for/rating/total_reviews/product_image/rakuten_url）+ rakuten_live.json のライブ最安から比較表を生成。product_image と価格が無い項目（vs比較記事）は除外。2行未満なら空を返しフォールバック
- `layouts/_default/single.html`: hub記事で本文最初の `<div class="table-scroll">…</table></div>` を hub_compare 出力に置換（regex置換、$は$$エスケープ済み）。$pages→$hubPages に共有化
- `layouts/_default/baseof.html`: `.table-scroll/.md-table` 汎用表CSS + `.cmp-*` 比較表CSS（sticky1列目・横スクロール・楽天ボタン）+ `.hub-card` の≤480pxボタン見切れ修正

## 検証済み
- hugo build成功、15/15ハブに `<table class="cmp">` 出現、フォールバック0
- vs記事等のmarkdown表は `.md-table` でスタイル適用
- スクショ確認済み（scratchpad/hub_desktop.png, hub_mobile.png）: デスクトップ表は740px内に収まる、モバイルはsticky商品列+スクロールヒント

## 残作業
1. hub-cardモバイル修正後の再ビルド+モバイル再スクショ確認（最後のCSS編集が未ビルド）
2. commit（conventional: feat:）+ push → GH Actions deploy
   - push認証: tyokomineは403。`gh auth token --user task-desk-lab` のcredential helperトリック（scripts/gen_priority_weekly.sh:22-27参照）
3. 本番URLで表示確認（https://taskdesklab.com/reviews/スピーカーフォン-おすすめ/）
4. 完了したらこのファイル削除 + company/taskdesklab_traffic_run.md のログに1行追記

## 既知の別問題（今回スコープ外・横峯さんに報告済みにする）
- rakuten_live.json の keyword検索が別商品を拾う（例: anker-powerconf min_price=9450 はPowerConf C200**ウェブカメラ**。jabra-speak2-75 も55と同額=55を拾っている疑い）。表・カード・単品ページ全てに出る既存問題。対策=バックログの「タイトル照合ゲート」をrakuten_live生成側にも
