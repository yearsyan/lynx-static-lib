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
