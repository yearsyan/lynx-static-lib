import { pluginReactLynx } from "@lynx-js/react-rsbuild-plugin";
import { defineConfig } from "@lynx-js/rspeedy";
import { pluginSass } from "@rsbuild/plugin-sass";

export default defineConfig({
  source: {
    entry: {
      main: "./src/index.tsx",
    },
  },
  output: {
    distPath: {
      root: "./dist",
    },
  },
  plugins: [
    pluginReactLynx({
      defaultDisplayLinear: false,
    }),
    pluginSass(),
  ],
  environments: {
    lynx: {},
  },
});
