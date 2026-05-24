import { root, useEffect, useMainThreadRef, useState } from "@lynx-js/react";

import "./styles.scss";

type HttpState = {
  status: string;
  detail: string;
};

type ProbeState = {
  effect: string;
  backgroundTap: string;
  autoFetch: string;
};

async function fetchHttpbinTitle(): Promise<HttpState> {
  "background only";
  const response = await fetch("https://httpbin.org/json", {
    headers: {
      Accept: "application/json",
      "X-Lynxlib-Demo": "curl-http-service",
    },
  });
  const text = await response.text();
  const body = JSON.parse(text);
  const title = body?.slideshow?.title ?? "body parsed";
  return {
    status: `HTTP ${response.status}`,
    detail: String(title),
  };
}

function describeError(error: unknown) {
  "background only";
  return error instanceof Error ? error.message : String(error);
}

function App() {
  const mainThreadTapCount = useMainThreadRef(0);
  const mainThreadPalettes = [
    {
      background: "#fff7ed",
      border: "#f97316",
      accent: "#fb923c",
    },
    {
      background: "#ecfeff",
      border: "#0891b2",
      accent: "#06b6d4",
    },
    {
      background: "#f0fdf4",
      border: "#16a34a",
      accent: "#22c55e",
    },
    {
      background: "#fdf2f8",
      border: "#db2777",
      accent: "#ec4899",
    },
  ];
  const [http, setHttp] = useState<HttpState>({
    status: "idle",
    detail: "tap Fetch to request httpbin",
  });
  const [probe, setProbe] = useState<ProbeState>({
    effect: "waiting for useEffect",
    backgroundTap: "waiting for bindtap",
    autoFetch: "waiting for timer",
  });

  useEffect(() => {
    "background only";
    console.log("[lynxlib-demo] mount useEffect log only");
    setProbe((current) => ({
      ...current,
      effect: "mounted in background thread",
    }));
    setTimeout(() => {
      "background only";
      console.log("[lynxlib-demo] auto fetch timer fired");
      startFetch("useEffect timer");
    }, 1000);
  }, []);

  function startFetch(trigger: string) {
    "background only";
    console.log(`[lynxlib-demo] fetch start trigger=${trigger}`);
    fetchHttpbinTitle()
      .then((next) => {
        console.log(`[lynxlib-demo] fetch success ${next.status}`);
        setHttp(next);
        setProbe((current) => ({
          ...current,
          autoFetch: `request completed from ${trigger}`,
        }));
      })
      .catch((error) => {
        console.log(`[lynxlib-demo] fetch failed ${describeError(error)}`);
        setHttp({
          status: "request failed",
          detail: describeError(error),
        });
        setProbe((current) => ({
          ...current,
          autoFetch: "request failed",
        }));
      });
  }

  function handleFetchTap() {
    "background only";
    console.log("[lynxlib-demo] Fetch tap handler invoked");
    setProbe((current) => ({
      ...current,
      backgroundTap: "background bindtap invoked",
    }));
    startFetch("Fetch bindtap");
  }

  function handleMainThreadColorTap(event: MainThread.ITouchEvent) {
    "main thread";
    const nextIndex = (mainThreadTapCount.current + 1) % mainThreadPalettes.length;
    mainThreadTapCount.current = nextIndex;
    const palette = mainThreadPalettes[nextIndex];
    event.currentTarget.setStyleProperties({
      "background-color": palette.background,
      "border-color": palette.border,
    });
    const swatch = event.currentTarget.querySelector(".mainThreadSwatch");
    if (swatch) {
      swatch.setStyleProperty("background-color", palette.accent);
    }
  }

  return (
    <view className="page">
      <view className="hero">
        <text className="eyebrow">lynxlib static sdk</text>
        <text className="title">Lynx static demo</text>
        <text className="subtitle">Native Win32 window</text>
        <text className="subtitle">Local bundle, static SDK link</text>
      </view>
      <view className="httpPanel">
        <view className="httpHeader">
          <text className="sectionTitle">HTTP service check</text>
          <view className="httpAction" bindtap={handleFetchTap}>
            <text className="httpActionText">Fetch</text>
          </view>
        </view>
        <text className="sampleText">{http.status}</text>
        <text className="sampleText">{http.detail}</text>
      </view>
      <view className="probePanel">
        <text className="sectionTitle">Runtime probes</text>
        <text className="sampleText">useEffect: {probe.effect}</text>
        <text className="sampleText">background tap: {probe.backgroundTap}</text>
        <text className="sampleText">auto fetch: {probe.autoFetch}</text>
      </view>
      <view
        className="mainThreadPanel"
        main-thread:bindtap={handleMainThreadColorTap}
      >
        <view className="mainThreadHeader">
          <view className="mainThreadSwatch" />
          <text className="sectionTitle">Main-thread tap</text>
        </view>
        <text className="sampleText">Tap updates this panel from the Lynx main thread.</text>
        <text className="sampleText">event.currentTarget.setStyleProperties()</text>
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
        <text className="footerText">Resize the window: content stays visible. Fetch uses lynxlib-http.</text>
      </view>
    </view>
  );
}

root.render(<App />);

if (import.meta.webpackHot) {
  import.meta.webpackHot.accept();
}
