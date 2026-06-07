/** Vue Router 路由配置：定义四个页面路由。 */
import { createRouter, createWebHistory } from "vue-router";

import ImportView from "../views/ImportView.vue";
import ProjectsView from "../views/ProjectsView.vue";
import WorkspaceView from "../views/WorkspaceView.vue";
import VersionsView from "../views/VersionsView.vue";

const router = createRouter({
  history: createWebHistory(),   // 使用 HTML5 History 模式
  routes: [
    {
      path: "/",
      name: "import",
      component: ImportView      // 导入页：上传小说并初始化项目
    },
    {
      path: "/projects",
      name: "projects",
      component: ProjectsView     // 项目列表页：管理所有项目
    },
    {
      path: "/workspace",
      name: "workspace",
      component: WorkspaceView    // 工作台：场景编辑、质量报告、YAML预览
    },
    {
      path: "/versions",
      name: "versions",
      component: VersionsView     // 版本记录页：版本列表与对比
    }
  ]
});

export default router;
