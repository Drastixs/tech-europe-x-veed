import { defineConfig } from "wxt";

export default defineConfig({
  modules: ["@wxt-dev/module-react"],
  manifest: {
    name: "Onshape Assist",
    description: "In-context assistive tutorial guidance for Onshape.",
    version: "0.1.0",
    minimum_chrome_version: "116",
    host_permissions: [
      "https://cad.onshape.com/documents/*",
      "http://127.0.0.1:8000/*"
    ],
    permissions: ["activeTab", "tabs"],
    action: { default_title: "Show Onshape Assist" }
  }
});
