import { root } from "@lynx-js/react";

import "./styles.scss";

function App() {
  return (
    <view className="page">
      <view className="hero">
        <text className="eyebrow">lynxlib static sdk</text>
        <text className="title">Lynx static demo</text>
        <text className="subtitle">Native Win32 window</text>
        <text className="subtitle">Local bundle, static SDK link</text>
      </view>
      <view className="grid">
        <view className="tile blue">
          <text className="tileLabel">Window</text>
          <text className="tileValue">Resizable</text>
        </view>
        <view className="tile green">
          <text className="tileLabel">SDK</text>
          <text className="tileValue">Static link</text>
        </view>
        <view className="tile gold">
          <text className="tileLabel">Bundle</text>
          <text className="tileValue">Local build</text>
        </view>
      </view>
      <view className="cjkPanel">
        <text className="sectionTitle">CJK render check</text>
        <text className="sampleText">中文：静态库渲染测试，中文标点与换行正常显示。</text>
        <text className="sampleText">日本語：静的ライブラリの表示テスト。かな・カナ・漢字を確認。</text>
        <text className="sampleText">한국어: 정적 라이브러리 렌더링 테스트, 한글 표시를 확인합니다.</text>
        <text className="sampleText">Mixed: English + 中文 + 日本語 + 한국어 + 12345</text>
      </view>
      <view className="footer">
        <text className="footerText">Resize the window: content stays visible.</text>
      </view>
    </view>
  );
}

root.render(<App />);

if (import.meta.webpackHot) {
  import.meta.webpackHot.accept();
}
