import { createRouter, createWebHistory } from "vue-router";

import ImportView from "../views/ImportView.vue";
import WorkspaceView from "../views/WorkspaceView.vue";
import VersionsView from "../views/VersionsView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "import",
      component: ImportView
    },
    {
      path: "/workspace",
      name: "workspace",
      component: WorkspaceView
    },
    {
      path: "/versions",
      name: "versions",
      component: VersionsView
    }
  ]
});

export default router;
